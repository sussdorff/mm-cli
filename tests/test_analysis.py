"""Tests for mm_cli.analysis module."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from mm_cli.analysis import compute_spending, get_previous_period, resolve_period
from mm_cli.models import (
    Category,
    CategoryType,
    SpendingAnalysis,
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
