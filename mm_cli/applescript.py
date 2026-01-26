"""AppleScript interface for MoneyMoney."""

import plistlib
import subprocess
from datetime import date
from decimal import Decimal
from pathlib import Path

from mm_cli.models import (
    Account,
    AccountType,
    Category,
    CategoryType,
    Transaction,
)


class AppleScriptError(Exception):
    """Raised when AppleScript execution fails."""

    pass


class MoneyMoneyNotRunningError(AppleScriptError):
    """Raised when MoneyMoney app is not running."""

    pass


def run_applescript(script: str) -> str:
    """Execute AppleScript via osascript and return the result.

    Args:
        script: The AppleScript code to execute.

    Returns:
        The output from the script.

    Raises:
        AppleScriptError: If the script fails to execute.
        MoneyMoneyNotRunningError: If MoneyMoney is not running.
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        if "MoneyMoney got an error" in error_msg:
            raise AppleScriptError(f"MoneyMoney error: {error_msg}") from e
        if "Application isn't running" in error_msg or "not running" in error_msg.lower():
            raise MoneyMoneyNotRunningError(
                "MoneyMoney is not running. Please start the application."
            ) from e
        raise AppleScriptError(f"AppleScript error: {error_msg}") from e


def _parse_plist_data(data: str | bytes) -> dict | list:
    """Parse plist data and return its contents.

    Args:
        data: Plist data as string or bytes.

    Returns:
        Parsed plist content.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    return plistlib.loads(data)


def _parse_plist_file(file_path: str) -> dict | list:
    """Parse a plist file and return its contents.

    Args:
        file_path: Path to the plist file.

    Returns:
        Parsed plist content.
    """
    path = Path(file_path)
    with path.open("rb") as f:
        return plistlib.load(f)


def _run_export_script(script: str) -> dict | list:
    """Run an export AppleScript and parse the plist result.

    MoneyMoney returns plist data directly as XML string.

    Args:
        script: AppleScript that returns plist data.

    Returns:
        Parsed plist content.
    """
    result = run_applescript(script)

    # MoneyMoney returns plist XML directly
    if result.startswith("<?xml") or result.startswith("<plist"):
        return _parse_plist_data(result)

    # Fallback: treat as file path (older behavior)
    return _parse_plist_file(result)


def _parse_account_type(type_str: str) -> AccountType:
    """Parse account type string to enum.

    Handles both English and German type names from MoneyMoney.
    """
    type_map = {
        # English names
        "checking": AccountType.CHECKING,
        "savings": AccountType.SAVINGS,
        "credit card": AccountType.CREDIT_CARD,
        "creditcard": AccountType.CREDIT_CARD,
        "cash": AccountType.CASH,
        "investment": AccountType.INVESTMENT,
        "depot": AccountType.INVESTMENT,
        "loan": AccountType.LOAN,
        # German names (as used by MoneyMoney)
        "girokonto": AccountType.CHECKING,
        "sparkonto": AccountType.SAVINGS,
        "tagesgeldkonto": AccountType.SAVINGS,
        "kreditkarte": AccountType.CREDIT_CARD,
        "bargeld": AccountType.CASH,
        "wertpapierdepot": AccountType.INVESTMENT,
        "kredit": AccountType.LOAN,
        "darlehen": AccountType.LOAN,
    }
    return type_map.get(type_str.lower(), AccountType.OTHER)


def _parse_category_type(type_int: int) -> CategoryType:
    """Parse category type integer to enum.

    MoneyMoney uses integers: 0 = expense, 1 = income
    """
    if type_int == 1:
        return CategoryType.INCOME
    return CategoryType.EXPENSE


def _extract_balance(balance_data: list | None) -> tuple[Decimal, str]:
    """Extract balance amount and currency from MoneyMoney balance structure.

    MoneyMoney returns balance as [[amount, currency]] (nested array).

    Args:
        balance_data: Balance data from plist.

    Returns:
        Tuple of (amount, currency).
    """
    if not balance_data:
        return Decimal("0"), "EUR"

    # Handle nested array: [[amount, currency]]
    if isinstance(balance_data, list) and len(balance_data) > 0:
        inner = balance_data[0]
        if isinstance(inner, list) and len(inner) >= 2:
            return Decimal(str(inner[0])), str(inner[1])
        elif isinstance(inner, (int, float)):
            # Simple [amount, currency] format
            currency = balance_data[1] if len(balance_data) > 1 else "EUR"
            return Decimal(str(inner)), str(currency)

    return Decimal("0"), "EUR"


def export_accounts() -> list[Account]:
    """Export all accounts from MoneyMoney.

    MoneyMoney returns a flat list where group items (group=True) act as
    section headers. All subsequent non-group items belong to the most
    recent group until a new group appears.

    Returns:
        List of Account objects with group names assigned.
    """
    script = 'tell application "MoneyMoney" to export accounts'
    data = _run_export_script(script)

    accounts = []
    current_group = ""

    for item in data:
        # Group items are section headers, not actual accounts
        if item.get("group", False):
            current_group = item.get("name", "")
            continue

        balance, currency = _extract_balance(item.get("balance"))
        account_num = item.get("accountNumber", "")
        iban = account_num if "DE" in str(account_num) else ""
        account = Account(
            id=str(item.get("uuid", account_num)),
            name=item.get("name", ""),
            account_number=account_num,
            bank_name=item.get("bankName", item.get("bankCode", "")),
            balance=balance,
            currency=currency,
            account_type=_parse_account_type(item.get("type", "other")),
            owner=item.get("owner", ""),
            iban=iban,
            bic=item.get("bankCode", ""),
            group=current_group,
            portfolio=item.get("portfolio", False),
        )
        accounts.append(account)

    return accounts


def export_categories() -> list[Category]:
    """Export all categories from MoneyMoney.

    MoneyMoney returns a flat list with 'indentation' levels (0, 1, 2, ...)
    to represent hierarchy. We reconstruct parent-child relationships from
    the indentation levels.

    Returns:
        List of Category objects with hierarchy information.
    """
    script = 'tell application "MoneyMoney" to export categories'
    data = _run_export_script(script)

    categories = []
    _parse_category_list(data, categories)
    return categories


def _parse_category_list(
    items: list,
    result: list[Category],
) -> None:
    """Parse flat category list using indentation levels to rebuild hierarchy.

    MoneyMoney exports categories as a flat list where each item has an
    'indentation' field (0 = root, 1 = child, 2 = grandchild, etc.).
    Items with 'group' = True are category folders/groups.

    Args:
        items: List of category dicts from plist.
        result: List to append Category objects to.
    """
    # Track parent stack: list of (id, name) at each indentation level
    parent_stack: list[tuple[str, str]] = []

    for item in items:
        cat_id = item.get("uuid", "")
        cat_name = item.get("name", "")
        indentation = item.get("indentation", 0)
        is_group = item.get("group", False)
        rules = item.get("rules", "")

        # Safely parse budget (dict with amount, period, available)
        budget = None
        budget_period = ""
        budget_available = None
        budget_raw = item.get("budget")
        if budget_raw is not None:
            if isinstance(budget_raw, dict):
                amount = budget_raw.get("amount")
                if amount is not None:
                    try:
                        budget = Decimal(str(amount))
                    except Exception:
                        pass
                budget_period = budget_raw.get("period", "")
                avail = budget_raw.get("available")
                if avail is not None:
                    try:
                        budget_available = Decimal(str(avail))
                    except Exception:
                        pass
            else:
                try:
                    budget = Decimal(str(budget_raw))
                except Exception:
                    pass

        # Trim parent stack to current indentation level
        parent_stack = parent_stack[:indentation]

        # Determine parent from stack
        parent_id = parent_stack[-1][0] if parent_stack else None
        parent_name = parent_stack[-1][1] if parent_stack else None

        # Build full path
        path_parts = [p[1] for p in parent_stack] + [cat_name]
        path = "\\".join(path_parts)

        category = Category(
            id=cat_id,
            name=cat_name,
            category_type=_parse_category_type(item.get("type", 0)),
            parent_id=parent_id,
            parent_name=parent_name,
            icon=str(item.get("icon", "")) if item.get("icon") else "",
            budget=budget,
            budget_period=budget_period,
            budget_available=budget_available,
            indentation=indentation,
            group=is_group,
            rules=rules,
            path=path,
        )
        result.append(category)

        # Push this category onto the parent stack for potential children
        parent_stack.append((cat_id, cat_name))


# Supported export formats for transactions
EXPORT_FORMATS = {"plist", "csv", "ofx", "sta", "xls", "numbers", "camt.053"}


def export_transactions(
    account_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    export_format: str = "plist",
) -> list[Transaction] | str:
    """Export transactions from MoneyMoney.

    Args:
        account_id: Optional account ID/IBAN to filter by.
        from_date: Optional start date.
        to_date: Optional end date.
        export_format: Export format - "plist" returns Transaction objects,
                      other formats ("csv", "ofx", "sta", "xls", "numbers", "camt.053")
                      return a file path to the exported file.

    Returns:
        List of Transaction objects for "plist" format,
        or file path string for other formats.

    Raises:
        ValueError: If export_format is not supported.
    """
    if export_format not in EXPORT_FORMATS:
        raise ValueError(
            f"Unsupported export format: {export_format}. "
            f"Supported formats: {', '.join(sorted(EXPORT_FORMATS))}"
        )

    # Build AppleScript command
    parts = ['tell application "MoneyMoney" to export transactions']

    if account_id:
        parts.append(f'from account "{account_id}"')

    if from_date:
        parts.append(f'from date "{from_date.isoformat()}"')

    if to_date:
        parts.append(f'to date "{to_date.isoformat()}"')

    parts.append(f'as "{export_format}"')

    script = " ".join(parts)

    # For non-plist formats, return the file path directly
    if export_format != "plist":
        return run_applescript(script)
    data = _run_export_script(script)

    # Transaction export returns a dict with 'transactions' key
    if isinstance(data, dict):
        tx_list = data.get("transactions", [])
    else:
        tx_list = data

    transactions = []
    for item in tx_list:
        # Parse dates - MoneyMoney returns datetime objects
        booking_date = item.get("bookingDate", date.today())
        value_date = item.get("valueDate", booking_date)

        # Handle datetime objects (convert to date)
        if hasattr(booking_date, "date"):
            booking_date = booking_date.date()
        elif isinstance(booking_date, str):
            booking_date = date.fromisoformat(booking_date[:10])

        if hasattr(value_date, "date"):
            value_date = value_date.date()
        elif isinstance(value_date, str):
            value_date = date.fromisoformat(value_date[:10])

        # Extract category name from path (e.g., "Haushalt\Ausgaben\Essen" -> "Essen")
        category_path = item.get("category", None)
        category_name = category_path.split("\\")[-1] if category_path else None

        transaction = Transaction(
            id=str(item.get("id", "")),
            account_id=str(item.get("accountUuid", "")),
            account_name=item.get("accountName", ""),
            booking_date=booking_date,
            value_date=value_date,
            amount=Decimal(str(item.get("amount", 0))),
            currency=item.get("currency", "EUR"),
            name=item.get("name", ""),
            purpose=item.get("purpose", ""),
            category_id=item.get("categoryUuid", None),
            category_name=category_name,
            checkmark=item.get("checkmark", False),
            comment=item.get("comment", ""),
            booked=item.get("booked", True),
            counterparty_iban=str(item.get("accountNumber", "")),
        )
        transactions.append(transaction)

    return transactions


def set_transaction_category(transaction_id: str, category_id: str) -> bool:
    """Set the category of a transaction.

    Args:
        transaction_id: The transaction ID.
        category_id: The category UUID.

    Returns:
        True if successful.

    Raises:
        AppleScriptError: If the operation fails.
    """
    script = (
        f'tell application "MoneyMoney" to set transaction id {transaction_id} '
        f'category to "{category_id}"'
    )
    run_applescript(script)
    return True


def set_transaction_checkmark(transaction_id: str, checked: bool) -> bool:
    """Set or clear the checkmark on a transaction.

    Args:
        transaction_id: The transaction ID.
        checked: True to set, False to clear.

    Returns:
        True if successful.
    """
    state = "on" if checked else "off"
    script = (
        f'tell application "MoneyMoney" to set transaction id {transaction_id} '
        f'checkmark to "{state}"'
    )
    run_applescript(script)
    return True


def set_transaction_comment(transaction_id: str, comment: str) -> bool:
    """Set a comment/note on a transaction.

    Args:
        transaction_id: The transaction ID.
        comment: The comment text.

    Returns:
        True if successful.
    """
    # Escape quotes in comment
    escaped_comment = comment.replace('"', '\\"')
    script = (
        f'tell application "MoneyMoney" to set transaction id {transaction_id} '
        f'comment to "{escaped_comment}"'
    )
    run_applescript(script)
    return True


def find_category_by_name(name: str) -> Category | None:
    """Find a category by name (case-insensitive partial match).

    Args:
        name: Category name to search for.

    Returns:
        Matching Category or None.
    """
    categories = export_categories()
    name_lower = name.lower()

    # First try exact match
    for cat in categories:
        if cat.name.lower() == name_lower:
            return cat

    # Then try partial match
    for cat in categories:
        if name_lower in cat.name.lower():
            return cat

    return None
