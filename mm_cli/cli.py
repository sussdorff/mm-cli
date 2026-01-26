"""Main CLI entrypoint for mm-cli."""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

import typer

from mm_cli import __version__
from mm_cli.analysis import compute_spending, get_previous_period, resolve_period
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
    output_spending,
    output_suggestions,
    output_transactions,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from mm_cli.rules import suggest_rules

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
    hierarchy: Annotated[
        bool,
        typer.Option("--hierarchy", help="Grouped display with section headers and subtotals"),
    ] = False,
    active: Annotated[
        bool,
        typer.Option("--active", help="Only active accounts (exclude 'Aufgelöst' group)"),
    ] = False,
    group: Annotated[
        list[str] | None,
        typer.Option("--group", "-g", help="Filter by account group (repeatable)"),
    ] = None,
) -> None:
    """List all accounts from MoneyMoney."""
    try:
        accs = export_accounts()

        # Filter by active (exclude "Aufgelöst" group)
        if active:
            accs = [a for a in accs if a.group.lower() != "aufgelöst"]

        # Filter by group name(s)
        if group:
            group_lower = [g.lower() for g in group]
            accs = [a for a in accs if a.group.lower() in group_lower]

        if not accs:
            print_warning("No accounts found matching the criteria.")
            return

        output_accounts(accs, format, hierarchy=hierarchy)
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
            txs = [tx for tx in txs if not tx.category_name]
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


@app.command("suggest-rules")
def suggest_rules_cmd(
    from_date: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Start date for uncategorized scan (YYYY-MM-DD)"),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", "-t", help="End date for uncategorized scan (YYYY-MM-DD)"),
    ] = None,
    history_months: Annotated[
        int,
        typer.Option("--history", "-H", help="Months of history to analyze for patterns"),
    ] = 6,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Suggest MoneyMoney rules based on uncategorized transactions.

    Analyzes uncategorized transactions and compares against categorized
    ones to suggest auto-categorization rules. Also checks existing rules
    for coverage gaps.

    Examples:
        mm suggest-rules --from 2026-01-01 --to 2026-01-31
        mm suggest-rules --history 12 --format json
    """
    try:
        # Parse dates
        start = parse_date(from_date) if from_date else None
        end = parse_date(to_date) if to_date else None

        # Get uncategorized transactions in the target range
        target_txs = export_transactions(from_date=start, to_date=end)
        uncategorized = [tx for tx in target_txs if not tx.category_name]

        if not uncategorized:
            print_warning("No uncategorized transactions found in the specified range.")
            return

        # Get historical categorized transactions for pattern matching
        # Go back history_months from the earliest uncategorized date
        from datetime import timedelta

        earliest = min(tx.booking_date for tx in uncategorized)
        history_start = earliest - timedelta(days=history_months * 30)

        all_txs = export_transactions(from_date=history_start, to_date=end)
        categorized = [tx for tx in all_txs if tx.category_name]

        # Get categories with existing rules
        cats = export_categories()

        print_info(
            f"Analyzing {len(uncategorized)} uncategorized transactions "
            f"against {len(categorized)} categorized ones ({history_months}mo history)..."
        )

        # Run the analysis
        suggestions = suggest_rules(uncategorized, categorized, cats)

        if not suggestions:
            print_warning("No rule suggestions could be generated.")
            return

        output_suggestions(suggestions, format)

    except Exception as e:
        handle_applescript_error(e)


analyze_app = typer.Typer(name="analyze", help="Analyze financial data")
app.add_typer(analyze_app)


@analyze_app.command("spending")
def analyze_spending(
    period: Annotated[
        str,
        typer.Option(
            "--period", "-p",
            help="Period: this-month, last-month, this-quarter, last-quarter, this-year",
        ),
    ] = "this-month",
    from_date: Annotated[
        str | None,
        typer.Option("--from", "-f", help="Override start date (YYYY-MM-DD)"),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option("--to", "-t", help="Override end date (YYYY-MM-DD)"),
    ] = None,
    compare: Annotated[
        bool,
        typer.Option("--compare", "-c", help="Compare with previous period"),
    ] = False,
    account: Annotated[
        str | None,
        typer.Option("--account", "-a", help="Filter by account ID or IBAN"),
    ] = None,
    group: Annotated[
        list[str] | None,
        typer.Option("--group", "-g", help="Filter by account group (repeatable)"),
    ] = None,
    type_filter: Annotated[
        str | None,
        typer.Option("--type", help="Filter: income or expense"),
    ] = None,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Analyze spending by category with optional budget comparison.

    Shows spending per category, optionally compared against budgets
    and/or the previous period.

    Examples:
        mm analyze spending
        mm analyze spending --period last-month
        mm analyze spending --compare
        mm analyze spending --type expense --group Privat
        mm analyze spending --from 2026-01-01 --to 2026-01-31
    """
    try:
        # Resolve date range
        if from_date or to_date:
            start = parse_date(from_date) if from_date else None
            end = parse_date(to_date) if to_date else None
            label = f"{start or '...'} to {end or '...'}"
        else:
            start, end, label = resolve_period(period)

        # Load accounts for group filtering
        account_ids: set[str] | None = None
        if group:
            accs = export_accounts()
            group_lower = [g.lower() for g in group]
            filtered_accs = [a for a in accs if a.group.lower() in group_lower]
            account_ids = {a.id for a in filtered_accs} | {a.iban for a in filtered_accs if a.iban}

        # Load transactions
        txs = export_transactions(
            account_id=account,
            from_date=start,
            to_date=end,
        )

        # Apply group filter
        if account_ids is not None:
            txs = [tx for tx in txs if tx.account_id in account_ids]

        # Apply type filter
        if type_filter:
            tf = type_filter.lower()
            if tf == "expense":
                txs = [tx for tx in txs if tx.amount < 0]
            elif tf == "income":
                txs = [tx for tx in txs if tx.amount > 0]

        if not txs:
            print_warning("No transactions found for the specified period.")
            return

        # Load categories for budget info
        cats = export_categories()

        # Comparison period
        compare_txs = None
        compare_label = None
        if compare and start and end:
            prev_start, prev_end, compare_label = get_previous_period(start, end)
            compare_txs = export_transactions(
                account_id=account,
                from_date=prev_start,
                to_date=prev_end,
            )
            if account_ids is not None:
                compare_txs = [tx for tx in compare_txs if tx.account_id in account_ids]
            if type_filter:
                tf = type_filter.lower()
                if tf == "expense":
                    compare_txs = [tx for tx in compare_txs if tx.amount < 0]
                elif tf == "income":
                    compare_txs = [tx for tx in compare_txs if tx.amount > 0]

        # Run analysis
        results = compute_spending(txs, cats, compare_txs)

        if not results:
            print_warning("No spending data to analyze.")
            return

        output_spending(results, label, format, compare_label=compare_label)

    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    except Exception as e:
        handle_applescript_error(e)


if __name__ == "__main__":
    app()
