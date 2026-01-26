"""Tests for mm_cli.applescript module."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from mm_cli.applescript import (
    AppleScriptError,
    MoneyMoneyNotRunningError,
    _parse_account_type,
    _parse_category_list,
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

    def test_parse_category_list(self, sample_plist_categories: list[dict]) -> None:
        """Test indentation-based category list parsing."""
        result: list[Category] = []
        _parse_category_list(sample_plist_categories, result)

        # Should have 4 categories (2 groups + 2 leaves)
        assert len(result) == 4

        # Check root group category
        parent = result[0]
        assert parent.name == "Einkommen"
        assert parent.parent_id is None
        assert parent.indentation == 0
        assert parent.group is True
        assert parent.path == "Einkommen"

        # Check child category
        child = result[1]
        assert child.name == "Gehalt"
        assert child.parent_id == parent.id
        assert child.parent_name == "Einkommen"
        assert child.indentation == 1
        assert child.group is False
        assert child.rules == "(Gehalt AND name:Cognovis)"
        assert child.path == "Einkommen\\Gehalt"

        # Check second root group
        parent2 = result[2]
        assert parent2.name == "Lebenshaltung"
        assert parent2.parent_id is None
        assert parent2.indentation == 0

        # Check second child
        child2 = result[3]
        assert child2.name == "Lebensmittel"
        assert child2.parent_name == "Lebenshaltung"
        assert child2.path == "Lebenshaltung\\Lebensmittel"
        assert child2.rules == "REWE OR Aldi"

    def test_parse_category_list_deep_hierarchy(self) -> None:
        """Test parsing categories with 3+ levels of nesting."""
        items = [
            {"uuid": "1", "name": "Root", "type": 0, "indentation": 0, "group": True, "rules": ""},
            {"uuid": "2", "name": "Mid", "type": 0, "indentation": 1, "group": True, "rules": ""},
            {"uuid": "3", "name": "Leaf", "type": 0, "indentation": 2, "group": False, "rules": "test rule"},
            {"uuid": "4", "name": "Other Root", "type": 0, "indentation": 0, "group": False, "rules": ""},
        ]
        result: list[Category] = []
        _parse_category_list(items, result)

        assert len(result) == 4
        assert result[0].path == "Root"
        assert result[1].path == "Root\\Mid"
        assert result[1].parent_name == "Root"
        assert result[2].path == "Root\\Mid\\Leaf"
        assert result[2].parent_name == "Mid"
        assert result[2].parent_id == "2"
        assert result[2].rules == "test rule"
        assert result[3].path == "Other Root"
        assert result[3].parent_id is None


class TestExportFunctions:
    """Tests for export functions with mocked AppleScript."""

    @patch("mm_cli.applescript._run_export_script")
    def test_export_accounts(
        self, mock_export: MagicMock, sample_plist_accounts: list[dict]
    ) -> None:
        """Test export_accounts parsing with group tracking."""
        mock_export.return_value = sample_plist_accounts

        accounts = export_accounts()

        # 3 actual accounts (groups are not included as accounts)
        assert len(accounts) == 3
        assert accounts[0].name == "Girokonto"
        assert accounts[0].balance == Decimal("1234.56")
        assert accounts[0].account_type == AccountType.CHECKING
        assert accounts[0].group == "Hauptkonten"

        assert accounts[1].name == "Tagesgeld"
        assert accounts[1].group == "Sparkonten"

        assert accounts[2].name == "Altes Konto"
        assert accounts[2].group == "Aufgelöst"

    @patch("mm_cli.applescript._run_export_script")
    def test_export_accounts_group_is_string(
        self, mock_export: MagicMock, sample_plist_accounts: list[dict]
    ) -> None:
        """Test that account group field is a string, not a boolean."""
        mock_export.return_value = sample_plist_accounts
        accounts = export_accounts()
        for acc in accounts:
            assert isinstance(acc.group, str)

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
    def test_export_categories_budget_parsing(
        self, mock_export: MagicMock, sample_plist_categories: list[dict]
    ) -> None:
        """Test budget period and available fields are parsed from plist."""
        mock_export.return_value = sample_plist_categories

        categories = export_categories()

        # Lebensmittel has budget data
        lebensmittel = [c for c in categories if c.name == "Lebensmittel"][0]
        assert lebensmittel.budget == Decimal("500.0")
        assert lebensmittel.budget_period == "monthly"
        assert lebensmittel.budget_available == Decimal("50.0")

        # Einkommen group has zero budget
        einkommen = [c for c in categories if c.name == "Einkommen"][0]
        assert einkommen.budget_period == "monthly"

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
