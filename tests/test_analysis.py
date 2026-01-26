"""Tests for mm_cli.analysis module."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from mm_cli.analysis import (
    compute_balance_history,
    compute_cashflow,
    compute_merchant_summary,
    compute_spending,
    compute_top_customers,
    detect_recurring,
    extract_transfers,
    filter_transfers,
    get_previous_period,
    get_transfer_category_ids,
    resolve_period,
)
from mm_cli.models import (
    Account,
    Category,
    CategoryType,
    Transaction,
)


class TestResolvePeriod:
    """Tests for resolve_period()."""

    @patch("mm_cli.analysis.date")
    def test_this_month(self, mock_date) -> None:
        mock_date.today.return_value = date(2026, 1, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        start, end, label = resolve_period("this-month")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 1, 31)
        assert "2026" in label

    @patch("mm_cli.analysis.date")
    def test_last_month(self, mock_date) -> None:
        mock_date.today.return_value = date(2026, 3, 10)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        start, end, label = resolve_period("last-month")
        assert start == date(2026, 2, 1)
        assert end == date(2026, 2, 28)

    @patch("mm_cli.analysis.date")
    def test_last_month_january(self, mock_date) -> None:
        mock_date.today.return_value = date(2026, 1, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        start, end, label = resolve_period("last-month")
        assert start == date(2025, 12, 1)
        assert end == date(2025, 12, 31)

    @patch("mm_cli.analysis.date")
    def test_this_quarter(self, mock_date) -> None:
        mock_date.today.return_value = date(2026, 5, 20)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        start, end, label = resolve_period("this-quarter")
        assert start == date(2026, 4, 1)
        assert end == date(2026, 6, 30)
        assert "Q2" in label

    @patch("mm_cli.analysis.date")
    def test_last_quarter_from_q1(self, mock_date) -> None:
        mock_date.today.return_value = date(2026, 2, 10)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        start, end, label = resolve_period("last-quarter")
        assert start == date(2025, 10, 1)
        assert end == date(2025, 12, 31)
        assert "Q4" in label

    @patch("mm_cli.analysis.date")
    def test_this_year(self, mock_date) -> None:
        mock_date.today.return_value = date(2026, 6, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        start, end, label = resolve_period("this-year")
        assert start == date(2026, 1, 1)
        assert end == date(2026, 12, 31)

    def test_invalid_period(self) -> None:
        with pytest.raises(ValueError, match="Unknown period"):
            resolve_period("invalid")


class TestGetPreviousPeriod:
    """Tests for get_previous_period()."""

    def test_monthly_period(self) -> None:
        start = date(2026, 3, 1)
        end = date(2026, 3, 31)
        prev_start, prev_end, label = get_previous_period(start, end)
        assert prev_start == date(2026, 2, 1)
        assert prev_end == date(2026, 2, 28)

    def test_january_previous(self) -> None:
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)
        prev_start, prev_end, label = get_previous_period(start, end)
        assert prev_start == date(2025, 12, 1)
        assert prev_end == date(2025, 12, 31)

    def test_arbitrary_range(self) -> None:
        start = date(2026, 1, 10)
        end = date(2026, 1, 20)
        prev_start, prev_end, label = get_previous_period(start, end)
        # 10-day range, shifts back by same duration
        assert prev_end == date(2026, 1, 9)
        assert (prev_end - prev_start).days == (end - start).days


class TestComputeSpending:
    """Tests for compute_spending()."""

    def test_basic_aggregation(self) -> None:
        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-45.00"),
                currency="EUR", name="REWE", purpose="Einkauf",
                category_id="cat-food", category_name="Lebensmittel",
            ),
            Transaction(
                id="2", account_id="acc1", booking_date=date(2026, 1, 10),
                value_date=date(2026, 1, 10), amount=Decimal("-30.00"),
                currency="EUR", name="Aldi", purpose="Einkauf",
                category_id="cat-food", category_name="Lebensmittel",
            ),
            Transaction(
                id="3", account_id="acc1", booking_date=date(2026, 1, 15),
                value_date=date(2026, 1, 15), amount=Decimal("3500.00"),
                currency="EUR", name="Gehalt", purpose="Lohn",
                category_id="cat-salary", category_name="Gehalt",
            ),
        ]
        cats = [
            Category(
                id="cat-food", name="Lebensmittel",
                category_type=CategoryType.EXPENSE,
                budget=Decimal("500"), budget_period="monthly",
            ),
            Category(
                id="cat-salary", name="Gehalt",
                category_type=CategoryType.INCOME,
            ),
        ]

        results = compute_spending(txs, cats)

        assert len(results) == 2
        # Sorted by absolute amount, salary first
        assert results[0].category_name == "Gehalt"
        assert results[0].actual == Decimal("3500.00")
        assert results[1].category_name == "Lebensmittel"
        assert results[1].actual == Decimal("-75.00")
        assert results[1].budget == Decimal("500")
        assert results[1].remaining == Decimal("425.00")
        assert results[1].transaction_count == 2

    def test_with_comparison(self) -> None:
        current = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-100.00"),
                currency="EUR", name="Store", purpose="",
                category_id="cat1", category_name="Shopping",
            ),
        ]
        compare = [
            Transaction(
                id="2", account_id="acc1", booking_date=date(2025, 12, 5),
                value_date=date(2025, 12, 5), amount=Decimal("-80.00"),
                currency="EUR", name="Store", purpose="",
                category_id="cat1", category_name="Shopping",
            ),
        ]
        cats = [
            Category(id="cat1", name="Shopping", category_type=CategoryType.EXPENSE),
        ]

        results = compute_spending(current, cats, compare)

        assert len(results) == 1
        assert results[0].compare_actual == Decimal("-80.00")
        assert results[0].compare_change == Decimal("25.0")  # 100/80 - 1 = 25%

    def test_uncategorized_transactions(self) -> None:
        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-20.00"),
                currency="EUR", name="Unknown", purpose="",
                category_id=None, category_name=None,
            ),
        ]
        results = compute_spending(txs, [])
        assert len(results) == 1
        assert results[0].category_name == "(Uncategorized)"


class TestComputeCashflow:
    """Tests for compute_cashflow()."""

    @patch("mm_cli.analysis.date")
    def test_monthly_cashflow(self, mock_date) -> None:
        mock_date.today.return_value = date(2025, 6, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2025, 5, 10),
                value_date=date(2025, 5, 10), amount=Decimal("3500.00"),
                currency="EUR", name="Salary", purpose="",
            ),
            Transaction(
                id="2", account_id="acc1", booking_date=date(2025, 5, 15),
                value_date=date(2025, 5, 15), amount=Decimal("-200.00"),
                currency="EUR", name="Shop", purpose="",
            ),
            Transaction(
                id="3", account_id="acc1", booking_date=date(2025, 6, 5),
                value_date=date(2025, 6, 5), amount=Decimal("-50.00"),
                currency="EUR", name="Cafe", purpose="",
            ),
        ]

        results = compute_cashflow(txs, months=3, granularity="monthly")

        assert len(results) >= 1
        # Find May entry
        may = [r for r in results if "2025-05" in r.period_label]
        assert len(may) == 1
        assert may[0].income == Decimal("3500.00")
        assert may[0].expenses == Decimal("-200.00")
        assert may[0].net == Decimal("3300.00")
        assert may[0].transaction_count == 2

    @patch("mm_cli.analysis.date")
    def test_quarterly_cashflow(self, mock_date) -> None:
        mock_date.today.return_value = date(2025, 6, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2025, 4, 10),
                value_date=date(2025, 4, 10), amount=Decimal("1000.00"),
                currency="EUR", name="Income", purpose="",
            ),
            Transaction(
                id="2", account_id="acc1", booking_date=date(2025, 5, 10),
                value_date=date(2025, 5, 10), amount=Decimal("-500.00"),
                currency="EUR", name="Expense", purpose="",
            ),
        ]

        results = compute_cashflow(txs, months=6, granularity="quarterly")

        assert len(results) >= 1
        q2 = [r for r in results if "Q2" in r.period_label]
        assert len(q2) == 1
        assert q2[0].income == Decimal("1000.00")
        assert q2[0].expenses == Decimal("-500.00")

    @patch("mm_cli.analysis.date")
    def test_empty_transactions(self, mock_date) -> None:
        mock_date.today.return_value = date(2025, 6, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        results = compute_cashflow([], months=3)
        assert results == []


class TestDetectRecurring:
    """Tests for detect_recurring()."""

    def test_detect_monthly_subscription(self) -> None:
        txs = []
        for m in range(1, 7):
            txs.append(Transaction(
                id=f"nf-{m}", account_id="acc1",
                booking_date=date(2025, m, 5),
                value_date=date(2025, m, 5),
                amount=Decimal("-12.99"),
                currency="EUR", name="NETFLIX.COM", purpose="Netflix",
                category_name="Streaming",
            ))

        results = detect_recurring(txs, min_occurrences=3)

        assert len(results) == 1
        assert results[0].merchant_name == "NETFLIX.COM"
        assert results[0].frequency == "monthly"
        assert results[0].occurrence_count == 6
        assert results[0].avg_amount == Decimal("-12.99")

    def test_below_threshold(self) -> None:
        txs = [
            Transaction(
                id="1", account_id="acc1",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-10.00"),
                currency="EUR", name="OneTime", purpose="",
            ),
            Transaction(
                id="2", account_id="acc1",
                booking_date=date(2025, 2, 5),
                value_date=date(2025, 2, 5),
                amount=Decimal("-10.00"),
                currency="EUR", name="OneTime", purpose="",
            ),
        ]
        results = detect_recurring(txs, min_occurrences=3)
        assert results == []

    def test_recurring_with_rich_fixture(self, rich_transactions) -> None:
        results = detect_recurring(rich_transactions, min_occurrences=3)
        # Should detect Netflix and salary at minimum
        names = [r.merchant_name for r in results]
        assert any("NETFLIX" in n for n in names)


class TestComputeMerchantSummary:
    """Tests for compute_merchant_summary()."""

    def test_basic_merchant_grouping(self) -> None:
        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5), amount=Decimal("-45.50"),
                currency="EUR", name="REWE", purpose="",
                category_name="Lebensmittel",
            ),
            Transaction(
                id="2", account_id="acc1", booking_date=date(2025, 1, 15),
                value_date=date(2025, 1, 15), amount=Decimal("-30.00"),
                currency="EUR", name="REWE", purpose="",
                category_name="Lebensmittel",
            ),
            Transaction(
                id="3", account_id="acc1", booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10), amount=Decimal("-12.99"),
                currency="EUR", name="NETFLIX.COM", purpose="",
                category_name="Streaming",
            ),
        ]

        results = compute_merchant_summary(txs, limit=20)

        assert len(results) == 2
        # REWE should be first (larger total)
        assert results[0].merchant_name == "REWE"
        assert results[0].transaction_count == 2
        assert results[0].total_amount == Decimal("-75.50")

    def test_type_filter_expense(self) -> None:
        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5), amount=Decimal("-50.00"),
                currency="EUR", name="Shop", purpose="",
            ),
            Transaction(
                id="2", account_id="acc1", booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10), amount=Decimal("3500.00"),
                currency="EUR", name="Salary", purpose="",
            ),
        ]

        results = compute_merchant_summary(txs, type_filter="expense")

        assert len(results) == 1
        assert results[0].merchant_name == "Shop"

    def test_limit(self) -> None:
        txs = [
            Transaction(
                id=str(i), account_id="acc1", booking_date=date(2025, 1, i + 1),
                value_date=date(2025, 1, i + 1), amount=Decimal(f"-{i * 10}"),
                currency="EUR", name=f"Merchant{i}", purpose="",
            )
            for i in range(1, 10)
        ]

        results = compute_merchant_summary(txs, limit=3)
        assert len(results) == 3


class TestComputeTopCustomers:
    """Tests for compute_top_customers()."""

    def test_top_customers_income_only(self) -> None:
        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10), amount=Decimal("5000.00"),
                currency="EUR", name="Big Client", purpose="Invoice",
                category_name="Rechnungen",
            ),
            Transaction(
                id="2", account_id="acc1", booking_date=date(2025, 2, 10),
                value_date=date(2025, 2, 10), amount=Decimal("3000.00"),
                currency="EUR", name="Big Client", purpose="Invoice",
                category_name="Rechnungen",
            ),
            Transaction(
                id="3", account_id="acc1", booking_date=date(2025, 1, 15),
                value_date=date(2025, 1, 15), amount=Decimal("1000.00"),
                currency="EUR", name="Small Client", purpose="Invoice",
                category_name="Rechnungen",
            ),
            Transaction(
                id="4", account_id="acc1", booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5), amount=Decimal("-50.00"),
                currency="EUR", name="Expense", purpose="",
            ),
        ]

        results = compute_top_customers(txs, limit=10)

        # Only income transactions (expenses filtered out)
        assert len(results) == 2
        assert results[0].merchant_name == "Big Client"
        assert results[0].total_amount == Decimal("8000.00")
        assert results[0].pct_of_total is not None
        # Big Client: 8000/9000 ~ 88.9%
        assert float(results[0].pct_of_total) == pytest.approx(88.9, abs=0.1)

    def test_no_income(self) -> None:
        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5), amount=Decimal("-50.00"),
                currency="EUR", name="Expense", purpose="",
            ),
        ]
        results = compute_top_customers(txs)
        assert results == []


class TestComputeBalanceHistory:
    """Tests for compute_balance_history()."""

    @patch("mm_cli.analysis.date")
    def test_single_account_history(self, mock_date) -> None:
        mock_date.today.return_value = date(2025, 3, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        accounts = [
            Account(
                id="acc1", name="Girokonto", account_number="123",
                bank_name="Bank", balance=Decimal("1000.00"),
                group="Hauptkonten",
            ),
        ]

        txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2025, 3, 5),
                value_date=date(2025, 3, 5), amount=Decimal("500.00"),
                currency="EUR", name="Income", purpose="",
            ),
            Transaction(
                id="2", account_id="acc1", booking_date=date(2025, 2, 10),
                value_date=date(2025, 2, 10), amount=Decimal("-200.00"),
                currency="EUR", name="Expense", purpose="",
            ),
        ]

        results = compute_balance_history(accounts, txs, months=3)

        assert len(results) == 3  # 3 months for 1 account
        assert all(r.account_name == "Girokonto" for r in results)

        # Most recent month should have current balance
        march = [r for r in results if "2025-03" in r.period_label]
        assert len(march) == 1
        assert march[0].balance == Decimal("1000.00")

    @patch("mm_cli.analysis.date")
    def test_empty_transactions(self, mock_date) -> None:
        mock_date.today.return_value = date(2025, 3, 15)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        accounts = [
            Account(
                id="acc1", name="Girokonto", account_number="123",
                bank_name="Bank", balance=Decimal("1000.00"),
            ),
        ]

        results = compute_balance_history(accounts, [], months=2)

        assert len(results) == 2
        # All snapshots should have the current balance (no changes)
        for r in results:
            assert r.balance == Decimal("1000.00")


class TestTransferFiltering:
    """Tests for get_transfer_category_ids and filter_transfers."""

    def test_get_transfer_category_ids(self) -> None:
        cats = [
            Category(
                id="cat-umbuchungen", name="Umbuchungen",
                category_type=CategoryType.EXPENSE,
                indentation=0, group=True,
                path="Umbuchungen",
            ),
            Category(
                id="cat-echte", name="Echte Umbuchung",
                category_type=CategoryType.EXPENSE,
                indentation=1, group=False,
                path="Umbuchungen\\Echte Umbuchung",
            ),
            Category(
                id="cat-kk", name="Kreditkarten Abrechnung",
                category_type=CategoryType.EXPENSE,
                indentation=1, group=False,
                path="Umbuchungen\\Kreditkarten Abrechnung",
            ),
            Category(
                id="cat-food", name="Lebensmittel",
                category_type=CategoryType.EXPENSE,
                path="Haushalt\\Lebensmittel",
            ),
        ]

        ids = get_transfer_category_ids(cats)

        assert ids == {"cat-umbuchungen", "cat-echte", "cat-kk"}
        assert "cat-food" not in ids

    def test_filter_transfers_removes_transfer_txs(self) -> None:
        transfer_ids = {"cat-kk", "cat-echte"}
        txs = [
            Transaction(
                id="1", account_id="acc1",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-45.00"),
                currency="EUR", name="REWE", purpose="",
                category_id="cat-food",
            ),
            Transaction(
                id="2", account_id="acc1",
                booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10),
                amount=Decimal("-2000.00"),
                currency="EUR",
                name="American Express",
                purpose="",
                category_id="cat-kk",
            ),
            Transaction(
                id="3", account_id="acc1",
                booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10),
                amount=Decimal("2000.00"),
                currency="EUR",
                name="Credit Card",
                purpose="",
                category_id="cat-kk",
            ),
        ]

        filtered = filter_transfers(txs, transfer_ids)

        assert len(filtered) == 1
        assert filtered[0].name == "REWE"

    def test_filter_transfers_keeps_uncategorized(self) -> None:
        """Transactions without a category_id should be kept."""
        transfer_ids = {"cat-kk"}
        txs = [
            Transaction(
                id="1", account_id="acc1",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-20.00"),
                currency="EUR", name="Unknown", purpose="",
                category_id=None,
            ),
        ]

        filtered = filter_transfers(txs, transfer_ids)

        assert len(filtered) == 1


class TestIBANTransferDetection:
    """Tests for IBAN-based transfer detection in filter_transfers."""

    def test_same_group_transfer_excluded(self, multi_group_accounts) -> None:
        """Transfer between accounts in the same group should be excluded."""
        txs = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-1000.00"),
                currency="EUR", name="Umbuchung",
                purpose="Spareinlage",
                counterparty_iban="DE27100777770209299700",  # Privat Tagesgeld
            ),
        ]
        filtered = filter_transfers(
            txs, set(),
            accounts=multi_group_accounts,
            active_groups=["Privat"],
        )
        assert len(filtered) == 0

    def test_cross_group_transfer_kept(self, multi_group_accounts) -> None:
        """Transfer from cognovis to Privat (salary) should be kept when groups active."""
        txs = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 28),
                value_date=date(2025, 1, 28),
                amount=Decimal("3500.00"),
                currency="EUR", name="cognovis GmbH",
                purpose="Gehalt",
                counterparty_iban="DE55370400440999888777",  # cognovis account
            ),
        ]
        filtered = filter_transfers(
            txs, set(),
            accounts=multi_group_accounts,
            active_groups=["Privat"],
        )
        assert len(filtered) == 1
        assert filtered[0].name == "cognovis GmbH"

    def test_cross_group_excluded_no_active_groups(self, multi_group_accounts) -> None:
        """Without active_groups, all own-account transfers are excluded."""
        txs = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 28),
                value_date=date(2025, 1, 28),
                amount=Decimal("3500.00"),
                currency="EUR", name="cognovis GmbH",
                purpose="Gehalt",
                counterparty_iban="DE55370400440999888777",  # cognovis account
            ),
        ]
        filtered = filter_transfers(
            txs, set(),
            accounts=multi_group_accounts,
            active_groups=None,
        )
        assert len(filtered) == 0

    def test_no_counterparty_iban_falls_back_to_category(self, multi_group_accounts) -> None:
        """Without counterparty IBAN, fall back to category-based detection."""
        transfer_ids = {"cat-kk-abrechnung"}
        txs = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 20),
                value_date=date(2025, 1, 20),
                amount=Decimal("-500.00"),
                currency="EUR", name="Amex",
                purpose="KK Abrechnung",
                category_id="cat-kk-abrechnung",
                counterparty_iban="",
            ),
        ]
        filtered = filter_transfers(
            txs, transfer_ids,
            accounts=multi_group_accounts,
            active_groups=["Privat"],
        )
        assert len(filtered) == 0

    def test_accounts_none_uses_category_only(self) -> None:
        """With accounts=None, only category-based filtering applies (backward compat)."""
        transfer_ids = {"cat-kk"}
        txs = [
            Transaction(
                id="1", account_id="acc1",
                booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10),
                amount=Decimal("-500.00"),
                currency="EUR", name="Amex",
                purpose="",
                category_id="cat-kk",
                counterparty_iban="DE89370400440532013000",
            ),
            Transaction(
                id="2", account_id="acc1",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-45.00"),
                currency="EUR", name="REWE",
                purpose="",
                category_id="cat-food",
            ),
        ]
        filtered = filter_transfers(txs, transfer_ids, accounts=None)
        assert len(filtered) == 1
        assert filtered[0].name == "REWE"

    def test_counterparty_not_own_account_kept(self, multi_group_accounts) -> None:
        """Transaction to an external IBAN should always be kept."""
        txs = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-45.00"),
                currency="EUR", name="REWE",
                purpose="Einkauf",
                counterparty_iban="DE12345678901234567890",  # not an own account
            ),
        ]
        filtered = filter_transfers(
            txs, set(),
            accounts=multi_group_accounts,
            active_groups=["Privat"],
        )
        assert len(filtered) == 1

    def test_mixed_scenario(self, multi_group_accounts) -> None:
        """End-to-end: mix of same-group, cross-group, external, and category-based."""
        transfer_ids = {"cat-kk-abrechnung"}
        txs = [
            # Same-group transfer (Privat -> Privat) => excluded
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-1000.00"),
                currency="EUR", name="Umbuchung",
                purpose="Spareinlage",
                counterparty_iban="DE27100777770209299700",
            ),
            # Cross-group transfer (cognovis -> Privat salary) => kept
            Transaction(
                id="2", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 28),
                value_date=date(2025, 1, 28),
                amount=Decimal("3500.00"),
                currency="EUR", name="cognovis GmbH",
                purpose="Gehalt",
                counterparty_iban="DE55370400440999888777",
            ),
            # External purchase => kept
            Transaction(
                id="3", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10),
                amount=Decimal("-45.00"),
                currency="EUR", name="REWE",
                purpose="Einkauf",
                counterparty_iban="DE12345678901234567890",
            ),
            # Category-based transfer (no IBAN) => excluded
            Transaction(
                id="4", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 20),
                value_date=date(2025, 1, 20),
                amount=Decimal("-500.00"),
                currency="EUR", name="Amex",
                purpose="KK Abrechnung",
                category_id="cat-kk-abrechnung",
                counterparty_iban="",
            ),
            # Normal expense (no IBAN, no transfer category) => kept
            Transaction(
                id="5", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 15),
                value_date=date(2025, 1, 15),
                amount=Decimal("-12.99"),
                currency="EUR", name="Netflix",
                purpose="Streaming",
                category_id="cat-streaming",
            ),
        ]
        filtered = filter_transfers(
            txs, transfer_ids,
            accounts=multi_group_accounts,
            active_groups=["Privat"],
        )
        assert len(filtered) == 3
        names = [tx.name for tx in filtered]
        assert "cognovis GmbH" in names
        assert "REWE" in names
        assert "Netflix" in names
        assert "Umbuchung" not in names
        assert "Amex" not in names


class TestExtractTransfers:
    """Tests for extract_transfers()."""

    def test_extract_returns_category_based_transfers(self, multi_group_accounts) -> None:
        """Transactions with a transfer category should be extracted."""
        transfer_ids = {"cat-kk-abrechnung"}
        txs = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 20),
                value_date=date(2025, 1, 20),
                amount=Decimal("-500.00"),
                currency="EUR", name="Amex",
                purpose="KK Abrechnung",
                category_id="cat-kk-abrechnung",
                counterparty_iban="",
            ),
            Transaction(
                id="2", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-45.00"),
                currency="EUR", name="REWE",
                purpose="Einkauf",
                category_id="cat-food",
            ),
        ]
        result = extract_transfers(txs, transfer_ids, accounts=multi_group_accounts)
        assert len(result) == 1
        assert result[0].name == "Amex"

    def test_extract_returns_iban_based_transfers(self, multi_group_accounts) -> None:
        """Transactions whose counterparty IBAN matches own accounts should be extracted."""
        txs = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-1000.00"),
                currency="EUR", name="Umbuchung",
                purpose="Spareinlage",
                counterparty_iban="DE27100777770209299700",  # Privat Tagesgeld
            ),
            Transaction(
                id="2", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10),
                amount=Decimal("-45.00"),
                currency="EUR", name="REWE",
                purpose="Einkauf",
                counterparty_iban="DE12345678901234567890",  # external
            ),
        ]
        result = extract_transfers(txs, set(), accounts=multi_group_accounts)
        assert len(result) == 1
        assert result[0].name == "Umbuchung"

    def test_extract_includes_cross_group_transfers(self, multi_group_accounts) -> None:
        """Cross-group transfers ARE included (no group exception in extract)."""
        txs = [
            # Cross-group transfer (cognovis -> Privat salary)
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 28),
                value_date=date(2025, 1, 28),
                amount=Decimal("3500.00"),
                currency="EUR", name="cognovis GmbH",
                purpose="Gehalt",
                counterparty_iban="DE55370400440999888777",  # cognovis account
            ),
            # Same-group transfer
            Transaction(
                id="2", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-1000.00"),
                currency="EUR", name="Umbuchung",
                purpose="Spareinlage",
                counterparty_iban="DE27100777770209299700",  # Privat Tagesgeld
            ),
        ]
        result = extract_transfers(txs, set(), accounts=multi_group_accounts)
        # Both are own-account transfers, both should be extracted
        assert len(result) == 2
        names = {tx.name for tx in result}
        assert "cognovis GmbH" in names
        assert "Umbuchung" in names

    def test_extract_excludes_external_transactions(self, multi_group_accounts) -> None:
        """External transactions should not be returned."""
        txs = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-45.00"),
                currency="EUR", name="REWE",
                purpose="Einkauf",
                counterparty_iban="DE12345678901234567890",  # external
                category_id="cat-food",
            ),
            Transaction(
                id="2", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 15),
                value_date=date(2025, 1, 15),
                amount=Decimal("-12.99"),
                currency="EUR", name="Netflix",
                purpose="Streaming",
                category_id="cat-streaming",
            ),
        ]
        result = extract_transfers(txs, set(), accounts=multi_group_accounts)
        assert len(result) == 0

    def test_extract_complement_of_filter(self, multi_group_accounts) -> None:
        """Without cross-group logic, extract + filter covers all transactions."""
        transfer_ids = {"cat-kk-abrechnung"}
        txs = [
            # IBAN-based own-account transfer
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5),
                amount=Decimal("-1000.00"),
                currency="EUR", name="Umbuchung",
                purpose="Spareinlage",
                counterparty_iban="DE27100777770209299700",
            ),
            # Category-based transfer (no IBAN)
            Transaction(
                id="2", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 20),
                value_date=date(2025, 1, 20),
                amount=Decimal("-500.00"),
                currency="EUR", name="Amex",
                purpose="KK Abrechnung",
                category_id="cat-kk-abrechnung",
                counterparty_iban="",
            ),
            # External purchase
            Transaction(
                id="3", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 10),
                value_date=date(2025, 1, 10),
                amount=Decimal("-45.00"),
                currency="EUR", name="REWE",
                purpose="Einkauf",
                counterparty_iban="DE12345678901234567890",
                category_id="cat-food",
            ),
            # Normal expense (no IBAN, no transfer category)
            Transaction(
                id="4", account_id="uuid-privat-giro",
                booking_date=date(2025, 1, 15),
                value_date=date(2025, 1, 15),
                amount=Decimal("-12.99"),
                currency="EUR", name="Netflix",
                purpose="Streaming",
                category_id="cat-streaming",
            ),
        ]
        extracted = extract_transfers(txs, transfer_ids, accounts=multi_group_accounts)
        # filter_transfers without active_groups doesn't have cross-group exception
        filtered = filter_transfers(
            txs, transfer_ids,
            accounts=multi_group_accounts,
            active_groups=None,
        )
        # Together they should cover all transactions
        extracted_ids = {tx.id for tx in extracted}
        filtered_ids = {tx.id for tx in filtered}
        all_ids = {tx.id for tx in txs}
        assert extracted_ids | filtered_ids == all_ids
        # And they should not overlap
        assert extracted_ids & filtered_ids == set()
