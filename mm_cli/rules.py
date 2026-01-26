"""Rule suggestion engine for MoneyMoney auto-categorization."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from mm_cli.models import Category, Transaction


@dataclass
class RuleSuggestion:
    """A suggested MoneyMoney rule for auto-categorization."""

    pattern: str
    suggested_category: str
    category_path: str
    match_count: int
    total_amount: Decimal
    confidence: str  # "high", "medium", "low"
    existing_rule: str  # existing rule text if category already has one
    sample_transactions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        result = {
            "pattern": self.pattern,
            "suggested_category": self.suggested_category,
            "category_path": self.category_path,
            "match_count": self.match_count,
            "total_amount": str(self.total_amount),
            "confidence": self.confidence,
        }
        if self.existing_rule:
            result["existing_rule"] = self.existing_rule
        if self.sample_transactions:
            result["sample_transactions"] = self.sample_transactions
        return result


def _normalize_name(name: str) -> str:
    """Normalize a payee name for matching.

    Strips location suffixes, card numbers, and common prefixes.
    """
    name = name.strip().lower()

    # Remove trailing country/city codes common in card transactions
    # e.g., "Apple.com.Bill/08006645451" -> "apple.com.bill"
    # e.g., "Amazon.de QL0TE44A5 LUX Luxembourg" -> "amazon.de"
    # Keep only the meaningful merchant identifier

    # Strip PayPal envelope to get merchant name
    if name.startswith("paypal *") or name.startswith("paypal*"):
        # "PayPal *Proshop S 87317327" -> "proshop"
        merchant = name.split("*", 1)[1].strip()
        # Remove trailing numbers/codes
        parts = merchant.split()
        # Keep first word(s) that look like a name
        clean_parts = []
        for part in parts:
            if part.isdigit() or (len(part) >= 3 and sum(c.isdigit() for c in part) > len(part) / 2):
                break
            clean_parts.append(part)
        return "paypal:" + " ".join(clean_parts) if clean_parts else name

    return name


def _extract_merchant_key(name: str) -> str:
    """Extract a stable merchant identifier for grouping similar transactions."""
    normalized = _normalize_name(name)

    # For PayPal transactions, use the merchant part
    if normalized.startswith("paypal:"):
        return normalized

    # For card transactions with location, take just the merchant
    # "Sehne.Backwaren.KG.Fil./Holzgerlingen" -> "sehne.backwaren"
    # "BK.19644.SOT/Malsfeld" -> "bk"
    if "/" in normalized:
        normalized = normalized.split("/")[0].strip()

    # Remove trailing transaction IDs
    # "Amazon.de QL0TE44A5 LUX Luxembourg" -> "amazon.de"
    parts = normalized.split()
    if len(parts) > 1:
        # Check if second part looks like a code
        clean_parts = [parts[0]]
        for part in parts[1:]:
            # Skip if it looks like a code (mixed alphanumeric, all caps short)
            if len(part) >= 5 and any(c.isdigit() for c in part) and any(c.isalpha() for c in part):
                break
            if part in ("lux", "luxembourg", "deu", "che", "esp", "gbr"):
                break
            clean_parts.append(part)
        normalized = " ".join(clean_parts)

    return normalized


def _check_existing_rules(pattern: str, categories: list[Category]) -> tuple[str, str, str]:
    """Check if a pattern is already covered by existing rules.

    Returns:
        Tuple of (category_name, category_path, rule_text) if found,
        or ("", "", "") if not covered.
    """
    pattern_lower = pattern.lower().strip('"')

    for cat in categories:
        if not cat.rules:
            continue
        rules_lower = cat.rules.lower()
        # Check if the pattern keyword appears in any existing rule
        if pattern_lower in rules_lower:
            return cat.name, cat.path, cat.rules

    return "", "", ""


def suggest_rules(
    uncategorized: list[Transaction],
    categorized: list[Transaction],
    categories: list[Category],
) -> list[RuleSuggestion]:
    """Analyze transactions and suggest MoneyMoney rules.

    Args:
        uncategorized: Transactions without categories.
        categorized: Transactions with categories assigned.
        categories: All categories (with existing rules).

    Returns:
        List of rule suggestions sorted by confidence and match count.
    """
    # Build name->category mapping from categorized transactions
    name_to_cats: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for tx in categorized:
        key = _extract_merchant_key(tx.name)
        # Find the category's full path
        cat_path = tx.category_name or ""
        for cat in categories:
            if cat.id == tx.category_id:
                cat_path = cat.path
                break
        name_to_cats[key].append((tx.category_name or "", cat_path))

    # Group uncategorized by merchant key
    uncat_groups: dict[str, list[Transaction]] = defaultdict(list)
    for tx in uncategorized:
        key = _extract_merchant_key(tx.name)
        uncat_groups[key].append(tx)

    suggestions: list[RuleSuggestion] = []
    seen_patterns: set[str] = set()

    for merchant_key, txs in uncat_groups.items():
        if merchant_key in seen_patterns:
            continue

        # Try to find a matching category from historical data
        suggested_cat = ""
        suggested_path = ""
        confidence = "low"

        # Exact merchant key match
        if merchant_key in name_to_cats:
            cat_entries = name_to_cats[merchant_key]
            most_common = Counter(c[0] for c in cat_entries).most_common(1)[0]
            suggested_cat = most_common[0]
            count = most_common[1]
            # Find the path
            for cat_name, cat_path in cat_entries:
                if cat_name == suggested_cat:
                    suggested_path = cat_path
                    break
            confidence = "high" if count >= 3 else "medium"
        else:
            # Try prefix match - find categorized merchants sharing a prefix
            for cat_key, cat_entries in name_to_cats.items():
                # Match if first 8+ chars match
                min_len = min(len(merchant_key), len(cat_key))
                if min_len >= 6 and merchant_key[:min(8, min_len)] == cat_key[:min(8, min_len)]:
                    most_common = Counter(c[0] for c in cat_entries).most_common(1)[0]
                    suggested_cat = most_common[0]
                    for cat_name, cat_path in cat_entries:
                        if cat_name == suggested_cat:
                            suggested_path = cat_path
                            break
                    confidence = "medium" if most_common[1] >= 2 else "low"
                    break

        # Build the rule pattern - use the original payee name from first transaction
        # Extract a clean pattern suitable for MoneyMoney rules
        first_name = txs[0].name.strip()
        if merchant_key.startswith("paypal:"):
            # For PayPal, suggest matching the merchant after PayPal *
            merchant_part = merchant_key.replace("paypal:", "")
            pattern = f'"PayPal *{merchant_part.title()}"'
        else:
            # Use the most common prefix across all transactions in this group
            names = [tx.name.strip() for tx in txs]
            if len(names) == 1:
                pattern = f'"{first_name}"'
            else:
                # Find common prefix
                prefix = names[0]
                for n in names[1:]:
                    while not n.lower().startswith(prefix.lower()) and len(prefix) > 3:
                        prefix = prefix[:-1]
                pattern = f'"{prefix.strip()}"' if len(prefix) > 3 else f'"{first_name}"'

        # Check if this pattern is already covered by existing rules
        existing_cat, existing_path, existing_rule = _check_existing_rules(
            pattern.strip('"'), categories
        )

        total = sum(tx.amount for tx in txs)

        # Build sample transactions
        samples = []
        for tx in txs[:3]:
            samples.append({
                "date": tx.booking_date.isoformat(),
                "name": tx.name,
                "amount": str(tx.amount),
                "purpose": tx.purpose[:60] if tx.purpose else "",
            })

        suggestion = RuleSuggestion(
            pattern=pattern,
            suggested_category=suggested_cat or "(needs manual assignment)",
            category_path=suggested_path,
            match_count=len(txs),
            total_amount=total,
            confidence=confidence if suggested_cat else "low",
            existing_rule=existing_rule,
            sample_transactions=samples,
        )
        suggestions.append(suggestion)
        seen_patterns.add(merchant_key)

    # Sort: high confidence first, then by match count, then by total amount
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    suggestions.sort(
        key=lambda s: (confidence_order.get(s.confidence, 3), -s.match_count, s.total_amount)
    )

    return suggestions
