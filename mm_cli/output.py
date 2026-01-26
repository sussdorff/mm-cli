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
from mm_cli.rules import RuleSuggestion

import sys as _sys

console = Console()
err_console = Console(stderr=True)


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
        print(json.dumps(data, indent=2, cls=DecimalEncoder))
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
        print(json.dumps(data, indent=2, cls=DecimalEncoder))
        return

    if format == OutputFormat.CSV:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "name", "path", "category_type", "parent_name", "group", "rules"],
        )
        writer.writeheader()
        for cat in categories:
            writer.writerow(
                {
                    "id": cat.id,
                    "name": cat.name,
                    "path": cat.path,
                    "category_type": cat.category_type.value,
                    "parent_name": cat.parent_name or "",
                    "group": cat.group,
                    "rules": cat.rules,
                }
            )
        console.print(output.getvalue())
        return

    # Table format - show hierarchy via indentation
    table = Table(title="Categories", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan", min_width=30)
    table.add_column("Rules", style="dim", max_width=40)
    table.add_column("ID", style="dim")

    for cat in categories:
        # Build indented name with tree characters
        indent = "  " * cat.indentation
        if cat.group:
            name_display = f"{indent}[bold]{cat.name}[/bold]"
        else:
            name_display = f"{indent}{cat.name}"

        # Truncate rules for display
        rules_display = cat.rules.replace("\n", " ").strip()[:40] if cat.rules else ""

        table.add_row(
            name_display,
            rules_display,
            cat.id[:8] + "...",
        )

    console.print(table)
    group_count = sum(1 for c in categories if c.group)
    leaf_count = len(categories) - group_count
    console.print(f"\n[dim]Total: {len(categories)} categories ({group_count} groups, {leaf_count} leaf)[/dim]")


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
        print(json.dumps(data, indent=2, cls=DecimalEncoder))
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
        print(json.dumps(data, indent=2, cls=DecimalEncoder))
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


def output_suggestions(
    suggestions: list[RuleSuggestion],
    format: OutputFormat = OutputFormat.TABLE,
) -> None:
    """Output rule suggestions in the specified format.

    Args:
        suggestions: List of rule suggestions to output.
        format: Output format.
    """
    if format == OutputFormat.JSON:
        data = [s.to_dict() for s in suggestions]
        print(json.dumps(data, indent=2, cls=DecimalEncoder))
        return

    if format == OutputFormat.CSV:
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "pattern", "suggested_category", "category_path",
                "match_count", "total_amount", "confidence", "existing_rule",
            ],
        )
        writer.writeheader()
        for s in suggestions:
            writer.writerow({
                "pattern": s.pattern,
                "suggested_category": s.suggested_category,
                "category_path": s.category_path,
                "match_count": s.match_count,
                "total_amount": str(s.total_amount),
                "confidence": s.confidence,
                "existing_rule": s.existing_rule.replace("\n", " ")[:60] if s.existing_rule else "",
            })
        console.print(output.getvalue())
        return

    # Table format
    # Split into sections by confidence
    has_existing = any(s.existing_rule for s in suggestions)
    new_rules = [s for s in suggestions if not s.existing_rule]
    existing_rules = [s for s in suggestions if s.existing_rule]

    if new_rules:
        table = Table(
            title="Suggested New Rules",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Pattern", style="cyan", min_width=25)
        table.add_column("Category", min_width=20)
        table.add_column("Path", style="dim", max_width=35)
        table.add_column("#", justify="right")
        table.add_column("Total", justify="right")
        table.add_column("Conf.")
        table.add_column("Samples", style="dim", max_width=40)

        for s in new_rules:
            conf_style = {"high": "green", "medium": "yellow", "low": "red"}
            conf_color = conf_style.get(s.confidence, "dim")

            # Build sample info
            sample_names = []
            for sample in s.sample_transactions[:2]:
                sample_names.append(f"{sample['date']} {sample['amount']}")
            sample_str = " | ".join(sample_names)

            table.add_row(
                s.pattern,
                s.suggested_category,
                s.category_path,
                str(s.match_count),
                format_currency(s.total_amount, "EUR"),
                f"[{conf_color}]{s.confidence}[/{conf_color}]",
                sample_str,
            )

        console.print(table)

    if existing_rules:
        console.print()
        table = Table(
            title="Already Covered by Existing Rules",
            show_header=True,
            header_style="bold",
        )
        table.add_column("Pattern", style="cyan", min_width=25)
        table.add_column("Existing Category", min_width=20)
        table.add_column("#", justify="right")
        table.add_column("Existing Rule", style="dim", max_width=50)

        for s in existing_rules:
            rule_preview = s.existing_rule.replace("\n", " ").strip()[:50]
            table.add_row(
                s.pattern,
                s.suggested_category,
                str(s.match_count),
                rule_preview,
            )

        console.print(table)

    # Summary
    console.print()
    total_uncat = sum(s.match_count for s in suggestions)
    covered = sum(s.match_count for s in existing_rules)
    new_matchable = sum(s.match_count for s in new_rules if s.confidence != "low")
    needs_manual = sum(s.match_count for s in new_rules if s.confidence == "low")
    console.print(f"[bold]Summary:[/bold] {total_uncat} uncategorized transactions")
    if covered:
        console.print(f"  Already covered by rules (not applied?): {covered}")
    console.print(f"  Matchable with new rules: {new_matchable}")
    console.print(f"  Need manual categorization: {needs_manual}")


def print_success(message: str) -> None:
    """Print a success message."""
    err_console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    err_console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    err_console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    err_console.print(f"[blue]ℹ[/blue] {message}")
