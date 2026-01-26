"""Tests for mm_cli.rules module."""

from datetime import date
from decimal import Decimal

from mm_cli.models import Category, Transaction
from mm_cli.rules import (
    RuleSuggestion,
    _check_existing_rules,
    _extract_merchant_key,
    _normalize_name,
    suggest_rules,
)


class TestNormalizeName:
    """Tests for payee name normalization."""

    def test_basic_name(self) -> None:
        assert _normalize_name("REWE") == "rewe"

    def test_paypal_merchant(self) -> None:
        result = _normalize_name("PayPal *Proshop S 87317327")
        assert result == "paypal:proshop s"

    def test_paypal_merchant_with_code(self) -> None:
        result = _normalize_name("PayPal *Merosstechn MER 02862050769")
        assert result == "paypal:merosstechn mer"

    def test_strips_whitespace(self) -> None:
        assert _normalize_name("  REWE  ") == "rewe"


class TestExtractMerchantKey:
    """Tests for merchant key extraction."""

    def test_simple_name(self) -> None:
        assert _extract_merchant_key("REWE") == "rewe"

    def test_name_with_location(self) -> None:
        result = _extract_merchant_key("Sehne.Backwaren.KG.Fil./Holzgerlingen")
        assert result == "sehne.backwaren.kg.fil."

    def test_name_with_country_code(self) -> None:
        result = _extract_merchant_key("Amazon.de QL0TE44A5 LUX Luxembourg")
        assert result == "amazon.de"

    def test_paypal_merchant(self) -> None:
        result = _extract_merchant_key("PayPal *LED24 0202610003")
        assert result == "paypal:led24"

    def test_bk_with_code(self) -> None:
        result = _extract_merchant_key("BK.19644.SOT/Malsfeld")
        assert result == "bk.19644.sot"


class TestCheckExistingRules:
    """Tests for checking if patterns are covered by existing rules."""

    def test_finds_matching_rule(self) -> None:
        cats = [
            Category(
                id="1", name="Einkaufen",
                rules='"REWE" OR Aldi OR Lidl',
                path="Haushalt\\Einkaufen",
            ),
        ]
        cat_name, cat_path, rule = _check_existing_rules("REWE", cats)
        assert cat_name == "Einkaufen"
        assert cat_path == "Haushalt\\Einkaufen"

    def test_no_match(self) -> None:
        cats = [
            Category(id="1", name="Einkaufen", rules='"REWE" OR Aldi'),
        ]
        cat_name, _, _ = _check_existing_rules("Amazon", cats)
        assert cat_name == ""

    def test_case_insensitive(self) -> None:
        cats = [
            Category(id="1", name="KI", rules='Anthropic OR OpenAI'),
        ]
        cat_name, _, _ = _check_existing_rules("anthropic", cats)
        assert cat_name == "KI"

    def test_skips_categories_without_rules(self) -> None:
        cats = [
            Category(id="1", name="Empty", rules=""),
            Category(id="2", name="HasRule", rules="test_pattern"),
        ]
        cat_name, _, _ = _check_existing_rules("test_pattern", cats)
        assert cat_name == "HasRule"


def _make_tx(
    name: str,
    category_name: str | None = None,
    category_id: str | None = None,
    amount: str = "-10.00",
    booking_date: date | None = None,
) -> Transaction:
    """Helper to create test transactions."""
    return Transaction(
        id="1",
        account_id="acc1",
        booking_date=booking_date or date(2026, 1, 15),
        value_date=booking_date or date(2026, 1, 15),
        amount=Decimal(amount),
        currency="EUR",
        name=name,
        purpose="test",
        category_id=category_id,
        category_name=category_name,
    )


class TestSuggestRules:
    """Tests for the main suggest_rules function."""

    def test_matches_exact_merchant(self) -> None:
        """Uncategorized tx with same merchant as categorized one gets suggestion."""
        uncategorized = [_make_tx("REWE")]
        categorized = [
            _make_tx("REWE", category_name="Einkaufen", category_id="cat1"),
            _make_tx("REWE", category_name="Einkaufen", category_id="cat1"),
        ]
        cats = [Category(id="cat1", name="Einkaufen", path="Haushalt\\Einkaufen")]

        suggestions = suggest_rules(uncategorized, categorized, cats)

        assert len(suggestions) == 1
        assert suggestions[0].suggested_category == "Einkaufen"
        assert suggestions[0].confidence in ("high", "medium")

    def test_no_match_yields_manual(self) -> None:
        """Completely unknown merchant gets 'needs manual assignment'."""
        uncategorized = [_make_tx("Unknown Corp")]
        categorized = [_make_tx("REWE", category_name="Einkaufen", category_id="cat1")]
        cats = []

        suggestions = suggest_rules(uncategorized, categorized, cats)

        assert len(suggestions) == 1
        assert suggestions[0].suggested_category == "(needs manual assignment)"
        assert suggestions[0].confidence == "low"

    def test_groups_same_merchant(self) -> None:
        """Multiple uncategorized txs from same merchant are grouped."""
        uncategorized = [
            _make_tx("Apple.com.Bill/08006645451", amount="-11.99"),
            _make_tx("Apple.com.Bill/08006645451", amount="-34.95"),
        ]
        categorized = []
        cats = []

        suggestions = suggest_rules(uncategorized, categorized, cats)

        assert len(suggestions) == 1
        assert suggestions[0].match_count == 2

    def test_detects_existing_rule_coverage(self) -> None:
        """Flags when a pattern is already in an existing rule."""
        uncategorized = [_make_tx("Jenny Sussdorff")]
        categorized = [
            _make_tx("Jenny Sussdorff", category_name="Haushalt Einzahlung", category_id="cat1"),
        ]
        cats = [
            Category(
                id="cat1", name="Haushalt Einzahlung",
                rules='name:"Jenny Sussdorff" AND Nebenkosten',
                path="Haushalt\\Haushalt Einnahmen\\Haushalt Einzahlung",
            ),
        ]

        suggestions = suggest_rules(uncategorized, categorized, cats)

        assert len(suggestions) == 1
        assert suggestions[0].existing_rule != ""

    def test_sorts_by_confidence(self) -> None:
        """High confidence suggestions come first."""
        uncategorized = [
            _make_tx("Unknown"),
            _make_tx("REWE"),
        ]
        categorized = [
            _make_tx("REWE", category_name="Einkaufen", category_id="cat1"),
            _make_tx("REWE", category_name="Einkaufen", category_id="cat1"),
            _make_tx("REWE", category_name="Einkaufen", category_id="cat1"),
        ]
        cats = [Category(id="cat1", name="Einkaufen", path="Einkaufen")]

        suggestions = suggest_rules(uncategorized, categorized, cats)

        assert len(suggestions) == 2
        assert suggestions[0].confidence == "high"
        assert suggestions[1].confidence == "low"

    def test_sample_transactions_included(self) -> None:
        """Suggestions include sample transaction details."""
        uncategorized = [_make_tx("Test Corp", amount="-50.00")]
        suggestions = suggest_rules(uncategorized, [], [])

        assert len(suggestions) == 1
        assert len(suggestions[0].sample_transactions) == 1
        assert suggestions[0].sample_transactions[0]["amount"] == "-50.00"

    def test_to_dict(self) -> None:
        """RuleSuggestion serialization works."""
        s = RuleSuggestion(
            pattern='"Test"',
            suggested_category="Cat",
            category_path="Parent\\Cat",
            match_count=2,
            total_amount=Decimal("-100"),
            confidence="high",
            existing_rule="",
        )
        d = s.to_dict()
        assert d["pattern"] == '"Test"'
        assert d["confidence"] == "high"
        assert "existing_rule" not in d  # empty rules excluded
