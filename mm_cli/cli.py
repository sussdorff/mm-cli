"""Main CLI entrypoint for mm-cli."""

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

import typer

from mm_cli import __version__
from mm_cli.analysis import (
    compute_balance_history,
    compute_cashflow,
    compute_merchant_summary,
    compute_spending,
    compute_top_customers,
    detect_recurring,
    filter_transfers,
    get_previous_period,
    get_transfer_category_ids,
    resolve_period,
)
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
    output_balance_history,
    output_cashflow,
    output_categories,
    output_category_usage,
    output_merchants,
    output_recurring,
    output_spending,
    output_suggestions,
    output_top_customers,
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
    include_transfers: Annotated[
        bool,
        typer.Option(
            "--include-transfers",
            help="Include internal transfers (Umbuchungen)",
        ),
    ] = False,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Analyze spending by category with optional budget comparison.

    Shows spending per category, optionally compared against budgets
    and/or the previous period. By default excludes internal transfers
    (Umbuchungen) which would distort the analysis.

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

        # Load accounts for group filtering and IBAN-based transfer detection
        all_accounts = None
        account_ids: set[str] | None = None
        if group or not include_transfers:
            all_accounts = export_accounts()
        if group and all_accounts:
            group_lower = [g.lower() for g in group]
            filtered_accs = [a for a in all_accounts if a.group.lower() in group_lower]
            account_ids = (
                {a.id for a in filtered_accs}
                | {a.iban for a in filtered_accs if a.iban}
                | {a.account_number for a in filtered_accs if a.account_number}
            )

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

        # Load categories for budget info and transfer filtering
        cats = export_categories()

        # Filter out internal transfers (Umbuchungen) unless opted in
        if not include_transfers:
            transfer_ids = get_transfer_category_ids(cats)
            txs = filter_transfers(txs, transfer_ids, accounts=all_accounts, active_groups=group)

        if not txs:
            print_warning("No transactions found for the specified period.")
            return

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
            if not include_transfers:
                compare_txs = filter_transfers(
                    compare_txs, transfer_ids,
                    accounts=all_accounts, active_groups=group,
                )
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


@analyze_app.command("cashflow")
def analyze_cashflow(
    months: Annotated[
        int,
        typer.Option("--months", "-m", help="Number of months to show"),
    ] = 6,
    period: Annotated[
        str,
        typer.Option("--period", "-p", help="Aggregation: monthly or quarterly"),
    ] = "monthly",
    group: Annotated[
        list[str] | None,
        typer.Option("--group", "-g", help="Filter by account group (repeatable)"),
    ] = None,
    include_transfers: Annotated[
        bool,
        typer.Option(
            "--include-transfers",
            help="Include internal transfers (Umbuchungen)",
        ),
    ] = False,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Show monthly/quarterly income vs expenses over time.

    By default excludes internal transfers (Umbuchungen) which would
    double-count money moved between own accounts.

    Examples:
        mm analyze cashflow
        mm analyze cashflow --months 12 --period quarterly
        mm analyze cashflow --group Privat
    """
    try:
        # Load accounts for group filtering and IBAN-based transfer detection
        all_accounts = None
        account_ids: set[str] | None = None
        if group or not include_transfers:
            all_accounts = export_accounts()
        if group and all_accounts:
            group_lower = [g.lower() for g in group]
            filtered_accs = [a for a in all_accounts if a.group.lower() in group_lower]
            account_ids = (
                {a.id for a in filtered_accs}
                | {a.iban for a in filtered_accs if a.iban}
                | {a.account_number for a in filtered_accs if a.account_number}
            )

        # Load transactions for the lookback period
        from datetime import timedelta

        today = date.today()
        start = (today.replace(day=1) - timedelta(days=(months - 1) * 30)).replace(day=1)
        txs = export_transactions(from_date=start, to_date=today)

        if account_ids is not None:
            txs = [tx for tx in txs if tx.account_id in account_ids]

        # Filter out internal transfers
        if not include_transfers:
            cats = export_categories()
            transfer_ids = get_transfer_category_ids(cats)
            txs = filter_transfers(txs, transfer_ids, accounts=all_accounts, active_groups=group)

        if not txs:
            print_warning("No transactions found for the specified period.")
            return

        results = compute_cashflow(txs, months=months, granularity=period)

        if not results:
            print_warning("No cashflow data to analyze.")
            return

        output_cashflow(results, format)

    except Exception as e:
        handle_applescript_error(e)


@analyze_app.command("recurring")
def analyze_recurring(
    months: Annotated[
        int,
        typer.Option("--months", "-m", help="Lookback period in months"),
    ] = 12,
    min_occurrences: Annotated[
        int,
        typer.Option("--min-occurrences", "-n", help="Minimum occurrences to qualify"),
    ] = 3,
    group: Annotated[
        list[str] | None,
        typer.Option("--group", "-g", help="Filter by account group (repeatable)"),
    ] = None,
    include_transfers: Annotated[
        bool,
        typer.Option(
            "--include-transfers",
            help="Include internal transfers (Umbuchungen)",
        ),
    ] = False,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Detect recurring transactions (subscriptions, standing orders).

    By default excludes internal transfers (Umbuchungen) like credit
    card settlements which are not real subscriptions.

    Examples:
        mm analyze recurring
        mm analyze recurring --months 6 --min-occurrences 4
        mm analyze recurring --group Privat
    """
    try:
        all_accounts = None
        account_ids: set[str] | None = None
        if group or not include_transfers:
            all_accounts = export_accounts()
        if group and all_accounts:
            group_lower = [g.lower() for g in group]
            filtered_accs = [a for a in all_accounts if a.group.lower() in group_lower]
            account_ids = (
                {a.id for a in filtered_accs}
                | {a.iban for a in filtered_accs if a.iban}
                | {a.account_number for a in filtered_accs if a.account_number}
            )

        from datetime import timedelta

        today = date.today()
        start = today - timedelta(days=months * 30)
        txs = export_transactions(from_date=start, to_date=today)

        if account_ids is not None:
            txs = [tx for tx in txs if tx.account_id in account_ids]

        # Filter out internal transfers
        if not include_transfers:
            cats = export_categories()
            transfer_ids = get_transfer_category_ids(cats)
            txs = filter_transfers(txs, transfer_ids, accounts=all_accounts, active_groups=group)

        if not txs:
            print_warning("No transactions found for the specified period.")
            return

        results = detect_recurring(txs, min_occurrences=min_occurrences)

        if not results:
            print_warning("No recurring transactions detected.")
            return

        output_recurring(results, format)

    except Exception as e:
        handle_applescript_error(e)


@analyze_app.command("merchants")
def analyze_merchants(
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
    type_filter: Annotated[
        str,
        typer.Option("--type", help="Filter: income, expense, or all"),
    ] = "expense",
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum merchants to show"),
    ] = 20,
    group: Annotated[
        list[str] | None,
        typer.Option("--group", "-g", help="Filter by account group (repeatable)"),
    ] = None,
    include_transfers: Annotated[
        bool,
        typer.Option(
            "--include-transfers",
            help="Include internal transfers (Umbuchungen)",
        ),
    ] = False,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Top merchants by total spend.

    Defaults to expense transactions only. Use --type all to include
    both income and expenses, or --type income for income only.

    Examples:
        mm analyze merchants
        mm analyze merchants --period this-year --limit 30
        mm analyze merchants --type all
        mm analyze merchants --from 2026-01-01 --to 2026-01-31
    """
    try:
        if from_date or to_date:
            start = parse_date(from_date) if from_date else None
            end = parse_date(to_date) if to_date else None
        else:
            start, end, _label = resolve_period(period)

        all_accounts = None
        account_ids: set[str] | None = None
        if group or not include_transfers:
            all_accounts = export_accounts()
        if group and all_accounts:
            group_lower = [g.lower() for g in group]
            filtered_accs = [a for a in all_accounts if a.group.lower() in group_lower]
            account_ids = (
                {a.id for a in filtered_accs}
                | {a.iban for a in filtered_accs if a.iban}
                | {a.account_number for a in filtered_accs if a.account_number}
            )

        txs = export_transactions(from_date=start, to_date=end)

        if account_ids is not None:
            txs = [tx for tx in txs if tx.account_id in account_ids]

        # Filter out internal transfers
        if not include_transfers:
            cats = export_categories()
            transfer_ids = get_transfer_category_ids(cats)
            txs = filter_transfers(txs, transfer_ids, accounts=all_accounts, active_groups=group)

        if not txs:
            print_warning("No transactions found for the specified period.")
            return

        # Pass None for "all" to show both income and expense
        effective_type = None if type_filter == "all" else type_filter
        results = compute_merchant_summary(
            txs, limit=limit, type_filter=effective_type,
        )

        if not results:
            print_warning("No merchant data to analyze.")
            return

        output_merchants(results, format)

    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    except Exception as e:
        handle_applescript_error(e)


@analyze_app.command("top-customers")
def analyze_top_customers(
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
    limit: Annotated[
        int,
        typer.Option("--limit", "-n", help="Maximum customers to show"),
    ] = 20,
    group: Annotated[
        list[str] | None,
        typer.Option("--group", "-g", help="Filter by account group (repeatable)"),
    ] = None,
    include_transfers: Annotated[
        bool,
        typer.Option(
            "--include-transfers",
            help="Include internal transfers (Umbuchungen)",
        ),
    ] = False,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Income grouped by counterparty (customer).

    Excludes internal transfers by default so credit card settlements
    don't appear as "customers".

    Examples:
        mm analyze top-customers
        mm analyze top-customers --period this-year --limit 10
        mm analyze top-customers --group cognovis
    """
    try:
        if from_date or to_date:
            start = parse_date(from_date) if from_date else None
            end = parse_date(to_date) if to_date else None
        else:
            start, end, _label = resolve_period(period)

        all_accounts = None
        account_ids: set[str] | None = None
        if group or not include_transfers:
            all_accounts = export_accounts()
        if group and all_accounts:
            group_lower = [g.lower() for g in group]
            filtered_accs = [a for a in all_accounts if a.group.lower() in group_lower]
            account_ids = (
                {a.id for a in filtered_accs}
                | {a.iban for a in filtered_accs if a.iban}
                | {a.account_number for a in filtered_accs if a.account_number}
            )

        txs = export_transactions(from_date=start, to_date=end)

        if account_ids is not None:
            txs = [tx for tx in txs if tx.account_id in account_ids]

        # Filter out internal transfers
        if not include_transfers:
            cats = export_categories()
            transfer_ids = get_transfer_category_ids(cats)
            txs = filter_transfers(txs, transfer_ids, accounts=all_accounts, active_groups=group)

        if not txs:
            print_warning("No transactions found for the specified period.")
            return

        results = compute_top_customers(txs, limit=limit)

        if not results:
            print_warning("No income transactions found.")
            return

        output_top_customers(results, format)

    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1) from e
    except Exception as e:
        handle_applescript_error(e)


@analyze_app.command("balance-history")
def analyze_balance_history(
    months: Annotated[
        int,
        typer.Option("--months", "-m", help="Number of months to show"),
    ] = 6,
    account: Annotated[
        str | None,
        typer.Option("--account", "-a", help="Filter by account name or IBAN"),
    ] = None,
    group: Annotated[
        list[str] | None,
        typer.Option("--group", "-g", help="Filter by account group (repeatable)"),
    ] = None,
    format: Annotated[
        OutputFormat,
        typer.Option("--format", help="Output format"),
    ] = OutputFormat.TABLE,
) -> None:
    """Approximate historical balance per account.

    Works backwards from current balance using transaction history.

    Examples:
        mm analyze balance-history
        mm analyze balance-history --months 12 --account Girokonto
        mm analyze balance-history --group Hauptkonten
    """
    try:
        accs = export_accounts()

        # Filter accounts
        if account:
            account_lower = account.lower()
            accs = [
                a for a in accs
                if account_lower in a.name.lower() or account_lower == a.iban.lower()
            ]
        if group:
            group_lower = [g.lower() for g in group]
            accs = [a for a in accs if a.group.lower() in group_lower]

        if not accs:
            print_warning("No accounts found matching the criteria.")
            return

        # Load transactions for lookback period
        from datetime import timedelta

        today = date.today()
        start = (today.replace(day=1) - timedelta(days=months * 30)).replace(day=1)
        account_ids = (
            {a.id for a in accs}
            | {a.iban for a in accs if a.iban}
            | {a.account_number for a in accs if a.account_number}
        )
        txs = export_transactions(from_date=start, to_date=today)
        txs = [tx for tx in txs if tx.account_id in account_ids]

        results = compute_balance_history(accs, txs, months=months)

        if not results:
            print_warning("No balance history data.")
            return

        output_balance_history(results, format)

    except Exception as e:
        handle_applescript_error(e)


if __name__ == "__main__":
    app()
