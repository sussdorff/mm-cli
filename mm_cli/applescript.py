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

    Args:
        script: AppleScript that returns a plist file path.

    Returns:
        Parsed plist content.
    """
    file_path = run_applescript(script)
    return _parse_plist_file(file_path)


def _parse_account_type(type_str: str) -> AccountType:
    """Parse account type string to enum."""
    type_map = {
        "checking": AccountType.CHECKING,
        "savings": AccountType.SAVINGS,
        "credit card": AccountType.CREDIT_CARD,
        "creditcard": AccountType.CREDIT_CARD,
        "cash": AccountType.CASH,
        "investment": AccountType.INVESTMENT,
        "depot": AccountType.INVESTMENT,
        "loan": AccountType.LOAN,
    }
    return type_map.get(type_str.lower(), AccountType.OTHER)


def _parse_category_type(type_int: int) -> CategoryType:
    """Parse category type integer to enum.

    MoneyMoney uses integers: 0 = expense, 1 = income
    """
    if type_int == 1:
        return CategoryType.INCOME
    return CategoryType.EXPENSE


def export_accounts() -> list[Account]:
    """Export all accounts from MoneyMoney.

    Returns:
        List of Account objects.
    """
    script = 'tell application "MoneyMoney" to export accounts'
    data = _run_export_script(script)

    accounts = []
    for item in data:
        balance_data = item.get("balance", [0, "EUR"])
        currency = balance_data[1] if isinstance(balance_data, list) else "EUR"
        account = Account(
            id=str(item.get("accountNumber", "")),
            name=item.get("name", ""),
            account_number=item.get("accountNumber", ""),
            bank_name=item.get("bankName", item.get("bankCode", "")),
            balance=Decimal(str(balance_data[0])),
            currency=currency,
            account_type=_parse_account_type(item.get("type", "other")),
            owner=item.get("owner", ""),
            iban=item.get("iban", ""),
            bic=item.get("bic", ""),
            group=item.get("group", ""),
            portfolio=item.get("portfolio", False),
        )
        accounts.append(account)

    return accounts


def export_categories() -> list[Category]:
    """Export all categories from MoneyMoney.

    Returns:
        List of Category objects.
    """
    script = 'tell application "MoneyMoney" to export categories'
    data = _run_export_script(script)

    categories = []
    _parse_category_tree(data, categories, parent_id=None, parent_name=None)
    return categories


def _parse_category_tree(
    items: list,
    result: list[Category],
    parent_id: str | None,
    parent_name: str | None,
) -> None:
    """Recursively parse category tree.

    Args:
        items: List of category dicts from plist.
        result: List to append Category objects to.
        parent_id: ID of parent category.
        parent_name: Name of parent category.
    """
    for item in items:
        cat_id = item.get("uuid", "")
        cat_name = item.get("name", "")

        category = Category(
            id=cat_id,
            name=cat_name,
            category_type=_parse_category_type(item.get("type", 0)),
            parent_id=parent_id,
            parent_name=parent_name,
            icon=item.get("icon", ""),
            budget=Decimal(str(item.get("budget"))) if item.get("budget") else None,
        )
        result.append(category)

        # Recursively process children
        children = item.get("children", [])
        if children:
            _parse_category_tree(children, result, cat_id, cat_name)


def export_transactions(
    account_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[Transaction]:
    """Export transactions from MoneyMoney.

    Args:
        account_id: Optional account ID/IBAN to filter by.
        from_date: Optional start date.
        to_date: Optional end date.

    Returns:
        List of Transaction objects.
    """
    # Build AppleScript command
    parts = ['tell application "MoneyMoney" to export transactions']

    if account_id:
        parts.append(f'from account "{account_id}"')

    if from_date:
        parts.append(f'from date "{from_date.isoformat()}"')

    if to_date:
        parts.append(f'to date "{to_date.isoformat()}"')

    parts.append('as "plist"')

    script = " ".join(parts)
    data = _run_export_script(script)

    transactions = []
    for item in data:
        # Parse dates
        booking_date = item.get("bookingDate", date.today())
        value_date = item.get("valueDate", booking_date)

        # Handle date objects vs strings
        if isinstance(booking_date, str):
            booking_date = date.fromisoformat(booking_date)
        if isinstance(value_date, str):
            value_date = date.fromisoformat(value_date)

        transaction = Transaction(
            id=str(item.get("id", "")),
            account_id=item.get("accountNumber", ""),
            account_name=item.get("accountName", ""),
            booking_date=booking_date,
            value_date=value_date,
            amount=Decimal(str(item.get("amount", 0))),
            currency=item.get("currency", "EUR"),
            name=item.get("name", ""),
            purpose=item.get("purpose", ""),
            category_id=item.get("categoryUuid", None),
            category_name=item.get("category", None),
            checkmark=item.get("checkmark", False),
            comment=item.get("comment", ""),
            booked=item.get("booked", True),
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
