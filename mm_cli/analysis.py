"""Financial analysis logic for mm-cli."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from mm_cli.models import Category, CategoryType, SpendingAnalysis, Transaction


def resolve_period(period_name: str) -> tuple[date, date, str]:
    """Convert a named period to a date range and display label.

    Args:
        period_name: One of "this-month", "last-month", "this-quarter",
                     "last-quarter", "this-year".

    Returns:
        Tuple of (start_date, end_date, label).

    Raises:
        ValueError: If period_name is not recognized.
    """
    today = date.today()

    if period_name == "this-month":
        start = today.replace(day=1)
        # End of current month: first of next month minus one day
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        label = today.strftime("%B %Y")

    elif period_name == "last-month":
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        label = start.strftime("%B %Y")

    elif period_name == "this-quarter":
        quarter = (today.month - 1) // 3
        start = today.replace(month=quarter * 3 + 1, day=1)
        end_month = quarter * 3 + 3
        if end_month == 12:
            end = today.replace(month=12, day=31)
        else:
            end = today.replace(month=end_month + 1, day=1) - timedelta(days=1)
        label = f"Q{quarter + 1} {today.year}"

    elif period_name == "last-quarter":
        quarter = (today.month - 1) // 3
        if quarter == 0:
            # Last quarter of previous year
            start = date(today.year - 1, 10, 1)
            end = date(today.year - 1, 12, 31)
            label = f"Q4 {today.year - 1}"
        else:
            prev_q = quarter - 1
            start = today.replace(month=prev_q * 3 + 1, day=1)
            end_month = prev_q * 3 + 3
            if end_month == 12:
                end = today.replace(month=12, day=31)
            else:
                end = today.replace(month=end_month + 1, day=1) - timedelta(days=1)
            label = f"Q{prev_q + 1} {today.year}"

    elif period_name == "this-year":
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)
        label = str(today.year)

    else:
        raise ValueError(
            f"Unknown period: {period_name}. "
            f"Use: this-month, last-month, this-quarter, last-quarter, this-year"
        )

    return start, end, label


def get_previous_period(start: date, end: date) -> tuple[date, date, str]:
    """Calculate the previous period of the same duration.

    For monthly periods, returns the previous month.
    For other durations, shifts back by the same number of days.

    Args:
        start: Start date of current period.
        end: End date of current period.

    Returns:
        Tuple of (prev_start, prev_end, label).
    """
    duration = (end - start).days

    # Detect monthly period (28-31 days, starts on 1st)
    if start.day == 1 and 27 <= duration <= 31:
        if start.month == 1:
            prev_start = date(start.year - 1, 12, 1)
            prev_end = date(start.year - 1, 12, 31)
        else:
            prev_start = start.replace(month=start.month - 1)
            if start.month - 1 == 12:
                prev_end = date(start.year, 12, 31)
            else:
                prev_end = start - timedelta(days=1)
        label = prev_start.strftime("%B %Y")
    else:
        # Generic: shift back by same duration
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=duration)
        label = f"{prev_start.isoformat()} - {prev_end.isoformat()}"

    return prev_start, prev_end, label


def compute_spending(
    transactions: list[Transaction],
    categories: list[Category],
    compare_transactions: list[Transaction] | None = None,
) -> list[SpendingAnalysis]:
    """Aggregate transactions by category and compute spending analysis.

    Args:
        transactions: Current period transactions.
        categories: All categories (for budget data).
        compare_transactions: Optional previous period transactions for comparison.

    Returns:
        List of SpendingAnalysis objects, sorted by absolute actual amount descending.
    """
    # Build category lookup
    cat_by_id: dict[str, Category] = {cat.id: cat for cat in categories}
    cat_by_name: dict[str, Category] = {cat.name: cat for cat in categories if not cat.group}

    # Aggregate current period
    current: dict[str, dict] = defaultdict(lambda: {
        "actual": Decimal("0"),
        "count": 0,
        "cat": None,
    })

    for tx in transactions:
        key = tx.category_name or "(Uncategorized)"
        current[key]["actual"] += tx.amount
        current[key]["count"] += 1
        if tx.category_id and tx.category_id in cat_by_id:
            current[key]["cat"] = cat_by_id[tx.category_id]
        elif not current[key]["cat"] and key in cat_by_name:
            current[key]["cat"] = cat_by_name[key]

    # Aggregate comparison period
    compare: dict[str, Decimal] = {}
    if compare_transactions:
        for tx in compare_transactions:
            key = tx.category_name or "(Uncategorized)"
            compare[key] = compare.get(key, Decimal("0")) + tx.amount

    # Build results
    results: list[SpendingAnalysis] = []
    for cat_name, data in current.items():
        cat = data["cat"]
        actual = data["actual"]
        count = data["count"]

        # Budget info from category
        budget = None
        budget_period = ""
        cat_path = cat_name
        cat_type = CategoryType.EXPENSE

        if cat:
            cat_path = cat.path or cat.name
            cat_type = cat.category_type
            if cat.budget and cat.budget > 0:
                budget = cat.budget
                budget_period = cat.budget_period

        # Calculate remaining and percent used
        remaining = None
        percent_used = None
        if budget and budget > 0:
            remaining = budget - abs(actual)
            percent_used = (abs(actual) / budget * 100).quantize(Decimal("0.1"))

        # Compare with previous period
        compare_actual = compare.get(cat_name) if compare else None
        compare_change = None
        if compare_actual is not None and compare_actual != 0:
            compare_change = (
                (abs(actual) - abs(compare_actual)) / abs(compare_actual) * 100
            ).quantize(Decimal("0.1"))

        results.append(SpendingAnalysis(
            category_name=cat_name,
            category_path=cat_path,
            category_type=cat_type,
            actual=actual,
            budget=budget,
            budget_period=budget_period,
            remaining=remaining,
            percent_used=percent_used,
            transaction_count=count,
            compare_actual=compare_actual,
            compare_change=compare_change,
        ))

    # Sort by absolute actual amount, descending
    results.sort(key=lambda r: abs(r.actual), reverse=True)

    return results
