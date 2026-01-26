"""Financial analysis logic for mm-cli."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from mm_cli.models import (
    Account,
    BalanceSnapshot,
    CashflowPeriod,
    Category,
    CategoryType,
    MerchantSummary,
    RecurringTransaction,
    SpendingAnalysis,
    Transaction,
)
from mm_cli.rules import _extract_merchant_key

TRANSFER_CATEGORY_ROOT = "Umbuchungen"


def get_transfer_category_ids(categories: list[Category]) -> set[str]:
    """Return category IDs that represent internal transfers.

    MoneyMoney uses a top-level "Umbuchungen" group containing categories
    like "Echte Umbuchung" and "Kreditkarten Abrechnung". Transactions
    in these categories are internal transfers between own accounts and
    should typically be excluded from cashflow/merchant analysis.
    """
    ids: set[str] = set()
    for cat in categories:
        if cat.path and cat.path.startswith(TRANSFER_CATEGORY_ROOT):
            ids.add(cat.id)
    return ids


def build_own_iban_set(accounts: list[Account]) -> set[str]:
    """Return a set of all own IBANs and account numbers."""
    result: set[str] = set()
    for acc in accounts:
        if acc.iban:
            result.add(acc.iban)
        if acc.account_number:
            result.add(acc.account_number)
    result.discard("")
    return result


def build_iban_to_group(accounts: list[Account]) -> dict[str, str]:
    """Map each own IBAN/account number to its group (lowercase)."""
    result: dict[str, str] = {}
    for acc in accounts:
        group = acc.group.lower()
        if acc.iban:
            result[acc.iban] = group
        if acc.account_number:
            result[acc.account_number] = group
    return result


def get_account_group(account_id: str, accounts: list[Account]) -> str:
    """Return the group name (lowercase) for a given account UUID."""
    for acc in accounts:
        if acc.id == account_id:
            return acc.group.lower()
    return ""


def filter_transfers(
    transactions: list[Transaction],
    transfer_category_ids: set[str],
    accounts: list[Account] | None = None,
    active_groups: list[str] | None = None,
) -> list[Transaction]:
    """Remove transactions that are internal transfers.

    Uses two detection methods:
    1. IBAN-based: if counterparty_iban matches one of our own accounts,
       it's a transfer. With active_groups, cross-group transfers are kept
       (they represent real cashflow like salary).
    2. Category-based fallback: if category_id is in transfer_category_ids.
    """
    if accounts is not None:
        own_ibans = build_own_iban_set(accounts)
        iban_to_group = build_iban_to_group(accounts)
        groups_lower = [g.lower() for g in active_groups] if active_groups else None
    else:
        own_ibans = set()

    result: list[Transaction] = []
    for tx in transactions:
        # IBAN-based detection
        if accounts is not None and tx.counterparty_iban and tx.counterparty_iban in own_ibans:
            if groups_lower:
                # Cross-group transfer check: keep if source and target are in different groups
                tx_group = get_account_group(tx.account_id, accounts)
                counterparty_group = iban_to_group.get(tx.counterparty_iban, "")
                if tx_group != counterparty_group:
                    # Cross-group: real cashflow, keep it
                    result.append(tx)
                # Same-group: internal shuffle, exclude
            # No active_groups: all own-account transfers excluded
            continue

        # Category-based fallback
        if tx.category_id in transfer_category_ids:
            continue

        result.append(tx)

    return result


def extract_transfers(
    transactions: list[Transaction],
    transfer_category_ids: set[str],
    accounts: list[Account] | None = None,
) -> list[Transaction]:
    """Return only transactions that are internal transfers.

    This is the complement of filter_transfers() — it keeps what
    filter_transfers() would remove, without the cross-group exception
    logic (since the caller explicitly wants to see all transfers).

    Uses two detection methods:
    1. IBAN-based: if counterparty_iban matches one of our own accounts.
    2. Category-based fallback: if category_id is in transfer_category_ids.
    """
    if accounts is not None:
        own_ibans = build_own_iban_set(accounts)
    else:
        own_ibans = set()

    result: list[Transaction] = []
    for tx in transactions:
        # IBAN-based detection
        if accounts is not None and tx.counterparty_iban and tx.counterparty_iban in own_ibans:
            result.append(tx)
            continue

        # Category-based fallback
        if tx.category_id in transfer_category_ids:
            result.append(tx)

    return result


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


def _month_label(d: date) -> str:
    """Return 'YYYY-MM' label for a date."""
    return d.strftime("%Y-%m")


def _quarter_label(d: date) -> str:
    """Return 'YYYY-QN' label for a date."""
    q = (d.month - 1) // 3 + 1
    return f"{d.year}-Q{q}"


def compute_cashflow(
    transactions: list[Transaction],
    months: int = 6,
    granularity: str = "monthly",
) -> list[CashflowPeriod]:
    """Aggregate transactions into income/expense per period.

    Args:
        transactions: All transactions (already filtered by account group if needed).
        months: Number of months to include.
        granularity: "monthly" or "quarterly".

    Returns:
        List of CashflowPeriod sorted by period chronologically.
    """
    today = date.today()
    cutoff = today.replace(day=1) - timedelta(days=(months - 1) * 30)
    cutoff = cutoff.replace(day=1)  # start of that month

    label_fn = _quarter_label if granularity == "quarterly" else _month_label

    buckets: dict[str, dict] = defaultdict(
        lambda: {"income": Decimal("0"), "expenses": Decimal("0"), "count": 0}
    )

    for tx in transactions:
        if tx.booking_date < cutoff:
            continue
        key = label_fn(tx.booking_date)
        if tx.amount > 0:
            buckets[key]["income"] += tx.amount
        else:
            buckets[key]["expenses"] += tx.amount
        buckets[key]["count"] += 1

    results = []
    for period_label in sorted(buckets):
        b = buckets[period_label]
        results.append(CashflowPeriod(
            period_label=period_label,
            income=b["income"],
            expenses=b["expenses"],
            net=b["income"] + b["expenses"],
            transaction_count=b["count"],
        ))

    return results


def detect_recurring(
    transactions: list[Transaction],
    min_occurrences: int = 3,
) -> list[RecurringTransaction]:
    """Detect recurring transactions (subscriptions, standing orders).

    Args:
        transactions: Transactions to analyze (already filtered by date range).
        min_occurrences: Minimum number of occurrences to qualify.

    Returns:
        List of RecurringTransaction sorted by annual cost descending.
    """
    # Group by merchant key
    merchant_txs: dict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        key = _extract_merchant_key(tx.name)
        merchant_txs[key].append(tx)

    results: list[RecurringTransaction] = []

    for _merchant_key, txs in merchant_txs.items():
        if len(txs) < min_occurrences:
            continue

        # Sort by date to analyze cadence
        txs.sort(key=lambda t: t.booking_date)

        # Calculate intervals between consecutive transactions
        intervals: list[int] = []
        for i in range(1, len(txs)):
            delta = (txs[i].booking_date - txs[i - 1].booking_date).days
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            continue

        avg_interval = sum(intervals) / len(intervals)

        # Determine frequency
        if avg_interval <= 45:  # ~monthly (allow variance)
            frequency = "monthly"
            annual_multiplier = 12
        elif avg_interval <= 120:  # ~quarterly
            frequency = "quarterly"
            annual_multiplier = 4
        else:
            frequency = "annual"
            annual_multiplier = 1

        amounts = [tx.amount for tx in txs]
        avg_amount = sum(amounts) / len(amounts)
        avg_amount = avg_amount.quantize(Decimal("0.01"))

        # Amount variance (std-dev-like: max - min)
        amount_variance = max(abs(a) for a in amounts) - min(abs(a) for a in amounts)

        total_annual_cost = (abs(avg_amount) * annual_multiplier).quantize(Decimal("0.01"))

        # Most common category
        cat_counts: dict[str, int] = defaultdict(int)
        for tx in txs:
            cat_counts[tx.category_name or "(Uncategorized)"] += 1
        category_name = max(cat_counts, key=cat_counts.get)  # type: ignore[arg-type]

        # Use original name of last transaction for display
        display_name = txs[-1].name

        results.append(RecurringTransaction(
            merchant_name=display_name,
            category_name=category_name,
            avg_amount=avg_amount,
            frequency=frequency,
            occurrence_count=len(txs),
            total_annual_cost=total_annual_cost,
            last_date=txs[-1].booking_date,
            amount_variance=amount_variance,
        ))

    # Sort by annual cost descending
    results.sort(key=lambda r: r.total_annual_cost, reverse=True)
    return results


def compute_merchant_summary(
    transactions: list[Transaction],
    limit: int = 20,
    type_filter: str | None = None,
) -> list[MerchantSummary]:
    """Group transactions by merchant and summarize.

    Args:
        transactions: Transactions to analyze.
        limit: Maximum results to return.
        type_filter: "income" or "expense" to pre-filter.

    Returns:
        List of MerchantSummary sorted by absolute total descending.
    """
    if type_filter == "income":
        transactions = [tx for tx in transactions if tx.amount > 0]
    elif type_filter == "expense":
        transactions = [tx for tx in transactions if tx.amount < 0]

    # Group by merchant key
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for tx in transactions:
        key = _extract_merchant_key(tx.name)
        groups[key].append(tx)

    results: list[MerchantSummary] = []
    for _key, txs in groups.items():
        total = sum(tx.amount for tx in txs)
        avg = (total / len(txs)).quantize(Decimal("0.01"))
        cats = sorted({tx.category_name or "(Uncategorized)" for tx in txs})
        dates = [tx.booking_date for tx in txs]
        # Use the most common original name for display
        name_counts: dict[str, int] = defaultdict(int)
        for tx in txs:
            name_counts[tx.name] += 1
        display_name = max(name_counts, key=name_counts.get)  # type: ignore[arg-type]

        results.append(MerchantSummary(
            merchant_name=display_name,
            transaction_count=len(txs),
            total_amount=total,
            avg_amount=avg,
            categories=cats,
            first_date=min(dates),
            last_date=max(dates),
        ))

    results.sort(key=lambda r: abs(r.total_amount), reverse=True)
    return results[:limit] if limit > 0 else results


def compute_top_customers(
    transactions: list[Transaction],
    limit: int = 20,
) -> list[MerchantSummary]:
    """Group income transactions by counterparty.

    Same as merchant summary but pre-filtered to income and with pct_of_total.

    Args:
        transactions: All transactions (income will be filtered).
        limit: Maximum results to return.

    Returns:
        List of MerchantSummary with pct_of_total populated.
    """
    income_txs = [tx for tx in transactions if tx.amount > 0]
    total_income = sum(tx.amount for tx in income_txs)

    results = compute_merchant_summary(income_txs, limit=limit)

    # Add percentage of total income
    if total_income > 0:
        for r in results:
            r.pct_of_total = (r.total_amount / total_income * 100).quantize(Decimal("0.1"))

    return results


def compute_balance_history(
    accounts: list[Account],
    transactions: list[Transaction],
    months: int = 6,
) -> list[BalanceSnapshot]:
    """Approximate historical month-end balances by working backwards.

    Args:
        accounts: Accounts with current balances.
        transactions: Transactions for the lookback period.
        months: Number of months to look back.

    Returns:
        List of BalanceSnapshot ordered by period then account.
    """
    today = date.today()

    # Build per-account transaction sums per month
    acct_monthly: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    acct_names: dict[str, str] = {}

    for acc in accounts:
        acct_names[acc.id] = acc.name

    for tx in transactions:
        key = _month_label(tx.booking_date)
        acct_monthly[tx.account_id][key] += tx.amount

    # Generate month labels (current month back to months ago)
    month_labels: list[str] = []
    d = today.replace(day=1)
    for _ in range(months):
        month_labels.append(_month_label(d))
        # Go to previous month
        d = (d - timedelta(days=1)).replace(day=1)
    month_labels.reverse()

    results: list[BalanceSnapshot] = []

    for acc in accounts:
        current_balance = acc.balance

        # Work backwards: subtract transactions from current month back
        # to reconstruct end-of-month balances
        snapshots: list[BalanceSnapshot] = []
        balance = current_balance

        # Process months from newest to oldest
        all_months = sorted(month_labels, reverse=True)
        for i, month in enumerate(all_months):
            month_sum = acct_monthly[acc.id].get(month, Decimal("0"))
            if i == 0:
                # Current month: balance is current balance
                snapshots.append(BalanceSnapshot(
                    period_label=month,
                    account_name=acc.name,
                    balance=balance,
                    change=month_sum,
                ))
            else:
                # Previous months: subtract this month's change to get end-of-prev-month
                balance = balance - month_sum
                prev_month_sum = acct_monthly[acc.id].get(all_months[i], Decimal("0"))
                snapshots.append(BalanceSnapshot(
                    period_label=month,
                    account_name=acc.name,
                    balance=balance,
                    change=prev_month_sum,
                ))

        # Reverse so they're chronological
        snapshots.reverse()
        results.extend(snapshots)

    return results
