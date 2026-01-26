"""Tests for mm_cli.applescript module."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from mm_cli.applescript import (
    AppleScriptError,
    MoneyMoneyNotRunningError,
    _extract_balance,
    _parse_account_type,
    _parse_category_list,
    _parse_category_type,
    export_accounts,
    export_categories,
    export_portfolio,
    export_transactions,
    find_category_by_name,
    run_applescript,
    set_transaction_category,
    set_transaction_checkmark,
    set_transaction_comment,
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
            {
                "uuid": "3", "name": "Leaf", "type": 0,
                "indentation": 2, "group": False, "rules": "test rule",
            },
            {
                "uuid": "4", "name": "Other Root", "type": 0,
                "indentation": 0, "group": False, "rules": "",
            },
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


class TestExportPortfolio:
    """Tests for export_portfolio function."""

    @patch("mm_cli.applescript._run_export_script")
    def test_export_portfolio_parsing(
        self, mock_export: MagicMock, sample_plist_portfolio: list[dict],
    ) -> None:
        """Test export_portfolio parses plist data correctly."""
        mock_export.return_value = sample_plist_portfolio

        portfolios = export_portfolio()

        assert len(portfolios) == 1
        p = portfolios[0]
        assert p.account_name == "Depot Commerzbank"
        assert p.account_id == "depot-uuid-1"
        assert len(p.securities) == 2

        # Check first security
        s1 = p.securities[0]
        assert s1.name == "iShares Core MSCI World"
        assert s1.isin == "IE00B4L5Y983"
        assert s1.quantity == 50.0
        assert s1.purchase_price == 65.00
        assert s1.current_price == 78.50
        assert s1.currency == "EUR"
        assert s1.market_value == 3925.00
        assert s1.asset_class == "Equity"

        # Gain/loss should be calculated
        expected_gain = 3925.00 - (50.0 * 65.00)
        assert s1.gain_loss == expected_gain

        # Check second security (negative gain)
        s2 = p.securities[1]
        assert s2.name == "Xtrackers DAX ETF"
        expected_gain2 = 2650.00 - (20.0 * 140.00)
        assert s2.gain_loss == expected_gain2
        assert s2.gain_loss < 0

    @patch("mm_cli.applescript._run_export_script")
    def test_export_portfolio_totals(
        self, mock_export: MagicMock, sample_plist_portfolio: list[dict],
    ) -> None:
        """Test that portfolio totals are computed correctly."""
        mock_export.return_value = sample_plist_portfolio

        portfolios = export_portfolio()

        p = portfolios[0]
        expected_total = 3925.00 + 2650.00
        assert p.total_value == expected_total
        assert p.total_gain_loss == sum(s.gain_loss for s in p.securities)

    @patch("mm_cli.applescript._run_export_script")
    def test_export_portfolio_with_account_id(self, mock_export: MagicMock) -> None:
        """Test export_portfolio builds correct AppleScript with account filter."""
        mock_export.return_value = []

        export_portfolio(account_id="test-uuid")

        call_args = mock_export.call_args[0][0]
        assert 'export portfolio of account id "test-uuid"' in call_args

    @patch("mm_cli.applescript._run_export_script")
    def test_export_portfolio_without_account_id(self, mock_export: MagicMock) -> None:
        """Test export_portfolio builds correct AppleScript without filter."""
        mock_export.return_value = []

        export_portfolio()

        call_args = mock_export.call_args[0][0]
        assert call_args == 'tell application "MoneyMoney" to export portfolio'

    @patch("mm_cli.applescript._run_export_script")
    def test_export_portfolio_empty_securities(self, mock_export: MagicMock) -> None:
        """Test export_portfolio with account that has no securities."""
        mock_export.return_value = [
            {"name": "Empty Depot", "uuid": "empty-uuid", "securities": []},
        ]

        portfolios = export_portfolio()

        assert len(portfolios) == 1
        assert portfolios[0].securities == []
        assert portfolios[0].total_value == 0.0
        assert portfolios[0].total_gain_loss == 0.0

    @patch("mm_cli.applescript._run_export_script")
    def test_export_portfolio_single_dict(self, mock_export: MagicMock) -> None:
        """Test export_portfolio handles single dict (filtered by account)."""
        mock_export.return_value = {
            "name": "Single Depot",
            "uuid": "single-uuid",
            "securities": [
                {
                    "name": "Test ETF",
                    "isin": "DE0001234567",
                    "quantity": 10.0,
                    "purchasePrice": 100.0,
                    "price": 110.0,
                    "currency": "EUR",
                    "marketValue": 1100.0,
                },
            ],
        }

        portfolios = export_portfolio()

        assert len(portfolios) == 1
        assert portfolios[0].account_name == "Single Depot"
        assert len(portfolios[0].securities) == 1


class TestSetTransactionCheckmark:
    """Tests for set_transaction_checkmark function."""

    @patch("mm_cli.applescript.run_applescript")
    def test_set_checkmark_on(self, mock_run: MagicMock) -> None:
        """Test setting checkmark to on."""
        mock_run.return_value = ""

        result = set_transaction_checkmark("12345", checked=True)

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "set transaction id 12345" in call_args
        assert 'checkmark to "on"' in call_args

    @patch("mm_cli.applescript.run_applescript")
    def test_set_checkmark_off(self, mock_run: MagicMock) -> None:
        """Test clearing checkmark (setting to off)."""
        mock_run.return_value = ""

        result = set_transaction_checkmark("12345", checked=False)

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "set transaction id 12345" in call_args
        assert 'checkmark to "off"' in call_args

    @patch("mm_cli.applescript.run_applescript")
    def test_set_checkmark_calls_applescript(self, mock_run: MagicMock) -> None:
        """Test that the correct AppleScript is constructed."""
        mock_run.return_value = ""

        set_transaction_checkmark("99999", checked=True)

        expected = (
            'tell application "MoneyMoney" to set transaction id 99999 '
            'checkmark to "on"'
        )
        mock_run.assert_called_once_with(expected)


class TestSetTransactionComment:
    """Tests for set_transaction_comment function."""

    @patch("mm_cli.applescript.run_applescript")
    def test_set_comment_simple(self, mock_run: MagicMock) -> None:
        """Test setting a simple comment."""
        mock_run.return_value = ""

        result = set_transaction_comment("12345", "test comment")

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "set transaction id 12345" in call_args
        assert 'comment to "test comment"' in call_args

    @patch("mm_cli.applescript.run_applescript")
    def test_set_comment_with_quotes(self, mock_run: MagicMock) -> None:
        """Test that double quotes in comments are escaped."""
        mock_run.return_value = ""

        set_transaction_comment("12345", 'He said "hello"')

        call_args = mock_run.call_args[0][0]
        assert 'comment to "He said \\"hello\\""' in call_args

    @patch("mm_cli.applescript.run_applescript")
    def test_set_comment_empty(self, mock_run: MagicMock) -> None:
        """Test setting an empty comment (clearing it)."""
        mock_run.return_value = ""

        result = set_transaction_comment("12345", "")

        assert result is True
        call_args = mock_run.call_args[0][0]
        assert 'comment to ""' in call_args

    @patch("mm_cli.applescript.run_applescript")
    def test_set_comment_calls_applescript(self, mock_run: MagicMock) -> None:
        """Test that the correct AppleScript is constructed."""
        mock_run.return_value = ""

        set_transaction_comment("54321", "Rechnung bezahlt")

        expected = (
            'tell application "MoneyMoney" to set transaction id 54321 '
            'comment to "Rechnung bezahlt"'
        )
        mock_run.assert_called_once_with(expected)


class TestExtractBalance:
    """Tests for _extract_balance helper function."""

    def test_nested_array_eur(self) -> None:
        """Test standard nested array format [[100.0, "EUR"]]."""
        amount, currency = _extract_balance([[100.0, "EUR"]])
        assert amount == Decimal("100.0")
        assert currency == "EUR"

    def test_nested_array_zero(self) -> None:
        """Test zero balance [[0, "EUR"]]."""
        amount, currency = _extract_balance([[0, "EUR"]])
        assert amount == Decimal("0")
        assert currency == "EUR"

    def test_nested_array_chf(self) -> None:
        """Test unusual currency [[500, "CHF"]]."""
        amount, currency = _extract_balance([[500, "CHF"]])
        assert amount == Decimal("500")
        assert currency == "CHF"

    def test_nested_array_usd(self) -> None:
        """Test USD currency [[1234.56, "USD"]]."""
        amount, currency = _extract_balance([[1234.56, "USD"]])
        assert amount == Decimal("1234.56")
        assert currency == "USD"

    def test_none_returns_default(self) -> None:
        """Test None balance returns (0, EUR) default."""
        amount, currency = _extract_balance(None)
        assert amount == Decimal("0")
        assert currency == "EUR"

    def test_empty_list_returns_default(self) -> None:
        """Test empty list returns (0, EUR) default."""
        amount, currency = _extract_balance([])
        assert amount == Decimal("0")
        assert currency == "EUR"

    def test_flat_array_format(self) -> None:
        """Test flat array format [amount, currency]."""
        amount, currency = _extract_balance([250.75, "EUR"])
        assert amount == Decimal("250.75")
        assert currency == "EUR"

    def test_flat_array_single_value(self) -> None:
        """Test flat array with single numeric value defaults to EUR."""
        amount, currency = _extract_balance([100.0])
        assert amount == Decimal("100.0")
        assert currency == "EUR"

    def test_negative_balance(self) -> None:
        """Test negative balance (e.g., credit card)."""
        amount, currency = _extract_balance([[-500.25, "EUR"]])
        assert amount == Decimal("-500.25")
        assert currency == "EUR"

    def test_large_balance(self) -> None:
        """Test large balance amount."""
        amount, currency = _extract_balance([[1000000.99, "EUR"]])
        assert amount == Decimal("1000000.99")
        assert currency == "EUR"
