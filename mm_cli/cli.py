"""Main CLI entrypoint for mm-cli."""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

import typer

from mm_cli import __version__
from mm_cli.applescript import (
    EXPORT_FORMATS,
    AppleScriptError,
    MoneyMoneyNotRunningError,
    export_accounts,
    export_categories,
    export_transactions,
    find_category_by_name,
    set_transaction_category,
)
from mm_cli.models import CategoryType, CategoryUsage
from mm_cli.output import (
    OutputFormat,
    output_accounts,
    output_categories,
    output_category_usage,
    output_transactions,
    print_error,
    print_info,
    print_success,
    print_warning,
)

app = typer.Typer(
    name="mm",
    help="CLI for MoneyMoney macOS app - manage accounts, transactions and categories",
    no_args_is_help=True,
)


def handle_applescript_error(e: Exception) -> None:
    """Handle AppleScript errors with user-friendly messages."""
    if isinstance(e, MoneyMoneyNotRunningError):
        print_error("MoneyMoney is not running. Please start the application first.")
        raise typer.Exit(1)
    elif isinstance(e, AppleScriptError):
        print_error(f"MoneyMoney error: {e}")
        raise typer.Exit(1)
    else:
        print_error(f"Unexpected error: {e}")
        raise typer.Exit(1)


def parse_date(date_str: str) -> date:
    """Parse a date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError as e:
        print_error(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
        raise typer.Exit(1) from e


@app.command()
def version() -> None:
    """Show version information."""
    typer.echo(f"mm-cli version {__version__}")


@app.command()
def accounts(
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """List all accounts from MoneyMoney."""
    try:
        accs = export_accounts()
        output_accounts(accs, format)
    except Exception as e:
        handle_applescript_error(e)


@app.command()
def categories(
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """List all categories from MoneyMoney."""
    try:
        cats = export_categories()
        output_categories(cats, format)
    except Exception as e:
        handle_applescript_error(e)


@app.command()
def transactions(
    account: Annotated[
        str | None,
        typer.Option("--account", "-a", help="Filter by account ID or IBAN"),
    ] = None,
    from_date: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Start date (YYYY-MM-DD)"),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", "-t", help="End date (YYYY-MM-DD)"),
    ] = None,
    category: Annotated[
        str | None,
        typer.Option("--category", "-c", help="Filter by category name"),
    ] = None,
    uncategorized: Annotated[
        bool,
        typer.Option("--uncategorized", "-u", help="Show only uncategorized transactions"),
    ] = False,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """List transactions with optional filtering."""
    try:
        # Parse dates if provided
        start = parse_date(from_date) if from_date else None
        end = parse_date(to_date) if to_date else None

        # Export transactions
        txs = export_transactions(
            account_id=account,
            from_date=start,
            to_date=end,
        )

        # Apply category filter
        if uncategorized:
            txs = [tx for tx in txs if not tx.category_id]
        elif category:
            category_lower = category.lower()
            txs = [
                tx for tx in txs if tx.category_name and category_lower in tx.category_name.lower()
            ]

        if not txs:
            print_warning("No transactions found matching the criteria.")
            return

        output_transactions(txs, format)

    except Exception as e:
        handle_applescript_error(e)


@app.command("category-usage")
def category_usage(
    from_date: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Start date (YYYY-MM-DD)"),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", "-t", help="End date (YYYY-MM-DD)"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Show top N categories"),
    ] = 20,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Show categories sorted by usage (transaction count)."""
    try:
        # Parse dates if provided
        start = parse_date(from_date) if from_date else None
        end = parse_date(to_date) if to_date else None

        # Get transactions
        txs = export_transactions(from_date=start, to_date=end)

        # Get categories for type info
        cats = export_categories()
        cat_types = {cat.id: cat.category_type for cat in cats}

        # Aggregate by category
        usage_map: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "total": Decimal("0"), "name": "", "type": CategoryType.EXPENSE}
        )

        for tx in txs:
            if tx.category_id:
                key = tx.category_id
                usage_map[key]["count"] += 1
                usage_map[key]["total"] += tx.amount
                usage_map[key]["name"] = tx.category_name or "Unknown"
                usage_map[key]["type"] = cat_types.get(key, CategoryType.EXPENSE)

        # Convert to CategoryUsage objects and sort
        usage_list = [
            CategoryUsage(
                category_id=cat_id,
                category_name=data["name"],
                transaction_count=data["count"],
                total_amount=data["total"],
                category_type=data["type"],
            )
            for cat_id, data in usage_map.items()
        ]

        # Sort by transaction count descending
        usage_list.sort(key=lambda u: u.transaction_count, reverse=True)

        # Apply limit
        if limit > 0:
            usage_list = usage_list[:limit]

        if not usage_list:
            print_warning("No categorized transactions found.")
            return

        output_category_usage(usage_list, format)

    except Exception as e:
        handle_applescript_error(e)


@app.command("export")
def export_file(
    account: Annotated[
        str | None,
        typer.Option("--account", "-a", help="Filter by account ID, IBAN, or name"),
    ] = None,
    from_date: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Start date (YYYY-MM-DD)"),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", "-t", help="End date (YYYY-MM-DD)"),
    ] = None,
    export_format: Annotated[
        str,
        typer.Option(
            "--format",
            help=f"Export format: {', '.join(sorted(EXPORT_FORMATS - {'plist'}))}",
        ),
    ] = "sta",
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output file path (default: print temp file path)"),
    ] = None,
) -> None:
    """Export transactions to a file (MT940, CSV, OFX, etc.).

    Exports transactions from MoneyMoney to various file formats.
    By default exports to MT940/STA format for import into accounting software.

    Examples:
        mm export --from 2024-01-01 --to 2024-12-31
        mm export -a "DE89370400440532013000" -f sta -o ~/transactions.sta
        mm export --format csv --from 2024-01-01
    """
    try:
        if export_format == "plist":
            print_error("Use 'mm transactions' command for plist/structured data.")
            raise typer.Exit(1)

        if export_format not in EXPORT_FORMATS:
            print_error(
                f"Unsupported format: {export_format}. "
                f"Supported: {', '.join(sorted(EXPORT_FORMATS - {'plist'}))}"
            )
            raise typer.Exit(1)

        # Parse dates
        start = parse_date(from_date) if from_date else None
        end = parse_date(to_date) if to_date else None

        # Export transactions
        result = export_transactions(
            account_id=account,
            from_date=start,
            to_date=end,
            export_format=export_format,
        )

        # Result is a file path for non-plist formats
        if isinstance(result, str):
            temp_path = result

            if output:
                # Copy to specified output path
                import shutil
                from pathlib import Path

                output_path = Path(output).expanduser()
                shutil.copy(temp_path, output_path)
                print_success(f"Exported to: {output_path}")
            else:
                # Just print the temp file path
                print_info(f"Exported to temporary file: {temp_path}")
                print_info("Use --output/-o to save to a specific location.")

    except Exception as e:
        handle_applescript_error(e)


@app.command("set-category")
def set_category(
    transaction_id: Annotated[
        str,
        typer.Argument(help="Transaction ID (from transactions export)"),
    ],
    category: Annotated[
        str,
        typer.Argument(help="Category name or UUID"),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be changed without applying"),
    ] = False,
) -> None:
    """Update the category of a transaction."""
    try:
        # Find category by name if not a UUID
        if len(category) < 32 or "-" not in category:
            cat = find_category_by_name(category)
            if not cat:
                print_error(f"Category not found: {category}")
                print_info("Use 'mm categories' to list available categories.")
                raise typer.Exit(1)
            category_id = cat.id
            category_name = cat.name
        else:
            category_id = category
            category_name = category

        if dry_run:
            print_info(f"Would set transaction {transaction_id} category to: {category_name}")
            print_info(f"Category ID: {category_id}")
            return

        # Apply the change
        set_transaction_category(transaction_id, category_id)
        print_success(f"Transaction {transaction_id} category set to: {category_name}")

    except Exception as e:
        handle_applescript_error(e)


if __name__ == "__main__":
    app()
