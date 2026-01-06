"""Tests for mm_cli.applescript module."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from mm_cli.applescript import (
    AppleScriptError,
    MoneyMoneyNotRunningError,
    _parse_account_type,
    _parse_category_tree,
    _parse_category_type,
    export_accounts,
    export_categories,
    export_transactions,
    find_category_by_name,
    run_applescript,
    set_transaction_category,
)
from mm_cli.models import AccountType, Category, CategoryType


class TestRunApplescript:
    """Tests for run_applescript function."""

    def test_successful_execution(self) -> None:
        """Test successful AppleScript execution."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="/tmp/test.plist\n", returncode=0)
            result = run_applescript('tell application "MoneyMoney" to export accounts')
            assert result == "/tmp/test.plist"

    def test_moneymoney_not_running(self) -> None:
        """Test error when MoneyMoney is not running."""
        with patch("subprocess.run") as mock_run:
            from subprocess import CalledProcessError

            error = CalledProcessError(1, "osascript")
            error.stderr = "Application isn't running"
            mock_run.side_effect = error

            with pytest.raises(MoneyMoneyNotRunningError):
                run_applescript('tell application "MoneyMoney" to export accounts')

    def test_applescript_error(self) -> None:
        """Test general AppleScript error handling."""
        with patch("subprocess.run") as mock_run:
            from subprocess import CalledProcessError

            error = CalledProcessError(1, "osascript")
            error.stderr = "MoneyMoney got an error: invalid transaction"
            mock_run.side_effect = error

            with pytest.raises(AppleScriptError, match="MoneyMoney error"):
                run_applescript("invalid script")


class TestParseHelpers:
    """Tests for parsing helper functions."""

    def test_parse_account_type_known_types(self) -> None:
        """Test parsing known account types."""
        assert _parse_account_type("checking") == AccountType.CHECKING
        assert _parse_account_type("savings") == AccountType.SAVINGS
        assert _parse_account_type("credit card") == AccountType.CREDIT_CARD
        assert _parse_account_type("creditcard") == AccountType.CREDIT_CARD
        assert _parse_account_type("depot") == AccountType.INVESTMENT

    def test_parse_account_type_unknown(self) -> None:
        """Test parsing unknown account type defaults to OTHER."""
        assert _parse_account_type("unknown") == AccountType.OTHER
        assert _parse_account_type("") == AccountType.OTHER

    def test_parse_category_type(self) -> None:
        """Test parsing category type integers."""
        assert _parse_category_type(0) == CategoryType.EXPENSE
        assert _parse_category_type(1) == CategoryType.INCOME

    def test_parse_category_tree(self, sample_plist_categories: list[dict]) -> None:
        """Test recursive category tree parsing."""
        result: list[Category] = []
        _parse_category_tree(sample_plist_categories, result, None, None)

        # Should have 4 categories (2 parents + 2 children)
        assert len(result) == 4

        # Check parent category
        parent = result[0]
        assert parent.name == "Einkommen"
        assert parent.parent_id is None

        # Check child category
        child = result[1]
        assert child.name == "Gehalt"
        assert child.parent_name == "Einkommen"


class TestExportFunctions:
    """Tests for export functions with mocked AppleScript."""

    @patch("mm_cli.applescript._run_export_script")
    def test_export_accounts(
        self, mock_export: MagicMock, sample_plist_accounts: list[dict]
    ) -> None:
        """Test export_accounts parsing."""
        mock_export.return_value = sample_plist_accounts

        accounts = export_accounts()

        assert len(accounts) == 1
        assert accounts[0].name == "Girokonto"
        assert accounts[0].balance == Decimal("1234.56")
        assert accounts[0].account_type == AccountType.CHECKING

    @patch("mm_cli.applescript._run_export_script")
    def test_export_categories(
        self, mock_export: MagicMock, sample_plist_categories: list[dict]
    ) -> None:
        """Test export_categories parsing."""
        mock_export.return_value = sample_plist_categories

        categories = export_categories()

        assert len(categories) == 4
        income_cats = [c for c in categories if c.category_type == CategoryType.INCOME]
        expense_cats = [c for c in categories if c.category_type == CategoryType.EXPENSE]
        assert len(income_cats) == 2
        assert len(expense_cats) == 2

    @patch("mm_cli.applescript._run_export_script")
    def test_export_transactions(
        self, mock_export: MagicMock, sample_plist_transactions: list[dict]
    ) -> None:
        """Test export_transactions parsing."""
        mock_export.return_value = sample_plist_transactions

        transactions = export_transactions()

        assert len(transactions) == 1
        tx = transactions[0]
        assert tx.id == "12345"
        assert tx.amount == Decimal("3500.00")
        assert tx.category_name == "Gehalt"

    @patch("mm_cli.applescript._run_export_script")
    def test_export_transactions_with_filters(self, mock_export: MagicMock) -> None:
        """Test export_transactions builds correct AppleScript with filters."""
        mock_export.return_value = []

        export_transactions(
            account_id="DE89370400440532013000",
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
        )

        # Verify the script was called with correct parameters
        call_args = mock_export.call_args[0][0]
        assert 'from account "DE89370400440532013000"' in call_args
        assert 'from date "2024-01-01"' in call_args
        assert 'to date "2024-12-31"' in call_args


class TestSetTransactionCategory:
    """Tests for set_transaction_category function."""

    @patch("mm_cli.applescript.run_applescript")
    def test_set_category_success(self, mock_run: MagicMock) -> None:
        """Test successful category update."""
        mock_run.return_value = ""

        result = set_transaction_category("12345", "test-uuid-1234")

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "set transaction id 12345 category to" in call_args
        assert "test-uuid-1234" in call_args


class TestFindCategoryByName:
    """Tests for find_category_by_name function."""

    @patch("mm_cli.applescript.export_categories")
    def test_exact_match(self, mock_export: MagicMock, sample_categories: list[Category]) -> None:
        """Test exact category name match."""
        mock_export.return_value = sample_categories

        result = find_category_by_name("Gehalt")

        assert result is not None
        assert result.name == "Gehalt"

    @patch("mm_cli.applescript.export_categories")
    def test_case_insensitive_match(
        self, mock_export: MagicMock, sample_categories: list[Category]
    ) -> None:
        """Test case-insensitive category name match."""
        mock_export.return_value = sample_categories

        result = find_category_by_name("gehalt")

        assert result is not None
        assert result.name == "Gehalt"

    @patch("mm_cli.applescript.export_categories")
    def test_partial_match(self, mock_export: MagicMock, sample_categories: list[Category]) -> None:
        """Test partial category name match."""
        mock_export.return_value = sample_categories

        result = find_category_by_name("lebens")

        assert result is not None
        assert "Lebens" in result.name

    @patch("mm_cli.applescript.export_categories")
    def test_no_match(self, mock_export: MagicMock, sample_categories: list[Category]) -> None:
        """Test no matching category found."""
        mock_export.return_value = sample_categories

        result = find_category_by_name("NonExistent")

        assert result is None
