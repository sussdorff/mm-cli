"""Output formatting utilities for mm-cli."""

import csv
import io
import json
from decimal import Decimal
from enum import Enum
from typing import Any

from rich.console import Console
from rich.table import Table

from mm_cli.models import Account, Category, CategoryUsage, Transaction

console = Console()


class OutputFormat(str, Enum):
    """Supported output formats."""

    TABLE = "table"
    JSON = "json"
    CSV = "csv"


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def format_currency(amount: Decimal, currency: str = "EUR") -> str:
    """Format a decimal amount as currency.

    Args:
        amount: The amount to format.
        currency: The currency code.

    Returns:
        Formatted currency string.
    """
    symbol_map = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}
    symbol = symbol_map.get(currency, currency)

    # Format with thousand separators and 2 decimal places
    formatted = f"{amount:,.2f}"

    # Color negative amounts red, positive green
    if amount < 0:
        return f"[red]{formatted} {symbol}[/red]"
    elif amount > 0:
        return f"[green]+{formatted} {symbol}[/green]"
    return f"{formatted} {symbol}"


def output_accounts(accounts: list[Account], format: OutputFormat = OutputFormat.TABLE) -> None:
    """Output accounts in the specified format.

    Args:
        accounts: List of accounts to output.
        format: Output format.
    """
    if format == OutputFormat.JSON:
        data = [acc.to_dict() for acc in accounts]
        console.print(json.dumps(data, indent=2, cls=DecimalEncoder))
        return

    if format == OutputFormat.CSV:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "name", "bank_name", "balance", "currency", "account_type", "iban"],
        )
        writer.writeheader()
        for acc in accounts:
            writer.writerow(
                {
                    "id": acc.id,
                    "name": acc.name,
                    "bank_name": acc.bank_name,
                    "balance": str(acc.balance),
                    "currency": acc.currency,
                    "account_type": acc.account_type.value,
                    "iban": acc.iban,
                }
            )
        console.print(output.getvalue())
        return

    # Table format (default)
    table = Table(title="Accounts", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Bank", style="dim")
    table.add_column("Type")
    table.add_column("Balance", justify="right")
    table.add_column("IBAN", style="dim")

    for acc in accounts:
        table.add_row(
            acc.name,
            acc.bank_name,
            acc.account_type.value,
            format_currency(acc.balance, acc.currency),
            acc.iban or "-",
        )

    console.print(table)

    # Print total
    total = sum(acc.balance for acc in accounts if acc.currency == "EUR")
    console.print(f"\n[bold]Total (EUR):[/bold] {format_currency(total, 'EUR')}")


def output_categories(
    categories: list[Category],
    format: OutputFormat = OutputFormat.TABLE,
) -> None:
    """Output categories in the specified format.

    Args:
        categories: List of categories to output.
        format: Output format.
    """
    if format == OutputFormat.JSON:
        data = [cat.to_dict() for cat in categories]
        console.print(json.dumps(data, indent=2, cls=DecimalEncoder))
        return

    if format == OutputFormat.CSV:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "name", "category_type", "parent_name"],
        )
        writer.writeheader()
        for cat in categories:
            writer.writerow(
                {
                    "id": cat.id,
                    "name": cat.name,
                    "category_type": cat.category_type.value,
                    "parent_name": cat.parent_name or "",
                }
            )
        console.print(output.getvalue())
        return

    # Table format - group by parent
    table = Table(title="Categories", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Type")
    table.add_column("Parent", style="dim")
    table.add_column("ID", style="dim")

    for cat in categories:
        type_style = "green" if cat.category_type.value == "income" else "red"
        indent = "  └ " if cat.parent_name else ""

        table.add_row(
            f"{indent}{cat.name}",
            f"[{type_style}]{cat.category_type.value}[/{type_style}]",
            cat.parent_name or "-",
            cat.id[:8] + "..." if len(cat.id) > 8 else cat.id,
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(categories)} categories[/dim]")


def output_transactions(
    transactions: list[Transaction],
    format: OutputFormat = OutputFormat.TABLE,
) -> None:
    """Output transactions in the specified format.

    Args:
        transactions: List of transactions to output.
        format: Output format.
    """
    if format == OutputFormat.JSON:
        data = [tx.to_dict() for tx in transactions]
        console.print(json.dumps(data, indent=2, cls=DecimalEncoder))
        return

    if format == OutputFormat.CSV:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id",
                "booking_date",
                "name",
                "purpose",
                "amount",
                "currency",
                "category_name",
                "account_name",
            ],
        )
        writer.writeheader()
        for tx in transactions:
            writer.writerow(
                {
                    "id": tx.id,
                    "booking_date": tx.booking_date.isoformat(),
                    "name": tx.name,
                    "purpose": tx.purpose,
                    "amount": str(tx.amount),
                    "currency": tx.currency,
                    "category_name": tx.category_name or "",
                    "account_name": tx.account_name,
                }
            )
        console.print(output.getvalue())
        return

    # Table format
    table = Table(title="Transactions", show_header=True, header_style="bold")
    table.add_column("Date", style="dim")
    table.add_column("Name", style="cyan", max_width=30)
    table.add_column("Purpose", max_width=40)
    table.add_column("Amount", justify="right")
    table.add_column("Category")
    table.add_column("Account", style="dim")

    for tx in transactions:
        check = "✓ " if tx.checkmark else ""
        category_display = tx.category_name or "[dim]uncategorized[/dim]"

        table.add_row(
            tx.booking_date.isoformat(),
            f"{check}{tx.name}",
            tx.purpose[:40] + "..." if len(tx.purpose) > 40 else tx.purpose,
            format_currency(tx.amount, tx.currency),
            category_display,
            tx.account_name or tx.account_id[:15],
        )

    console.print(table)

    # Print summary
    total = sum(tx.amount for tx in transactions)
    income = sum(tx.amount for tx in transactions if tx.amount > 0)
    expense = sum(tx.amount for tx in transactions if tx.amount < 0)

    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Transactions: {len(transactions)}")
    console.print(f"  Income: {format_currency(income, 'EUR')}")
    console.print(f"  Expenses: {format_currency(expense, 'EUR')}")
    console.print(f"  Net: {format_currency(total, 'EUR')}")


def output_category_usage(
    usage: list[CategoryUsage],
    format: OutputFormat = OutputFormat.TABLE,
) -> None:
    """Output category usage statistics.

    Args:
        usage: List of category usage stats.
        format: Output format.
    """
    if format == OutputFormat.JSON:
        data = [u.to_dict() for u in usage]
        console.print(json.dumps(data, indent=2, cls=DecimalEncoder))
        return

    if format == OutputFormat.CSV:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["category_name", "transaction_count", "total_amount", "category_type"],
        )
        writer.writeheader()
        for u in usage:
            writer.writerow(
                {
                    "category_name": u.category_name,
                    "transaction_count": u.transaction_count,
                    "total_amount": str(u.total_amount),
                    "category_type": u.category_type.value,
                }
            )
        console.print(output.getvalue())
        return

    # Table format
    table = Table(title="Category Usage", show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Category", style="cyan")
    table.add_column("Type")
    table.add_column("Transactions", justify="right")
    table.add_column("Total Amount", justify="right")

    for i, u in enumerate(usage, 1):
        type_style = "green" if u.category_type.value == "income" else "red"
        table.add_row(
            str(i),
            u.category_name,
            f"[{type_style}]{u.category_type.value}[/{type_style}]",
            str(u.transaction_count),
            format_currency(u.total_amount, "EUR"),
        )

    console.print(table)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]ℹ[/blue] {message}")
