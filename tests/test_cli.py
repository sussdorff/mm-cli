"""Tests for mm_cli.cli module."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mm_cli.cli import app
from mm_cli.models import Account, Category, CategoryType, Transaction

runner = CliRunner()


class TestVersionCommand:
    """Tests for version command."""

    def test_version(self) -> None:
        """Test version command output."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "mm-cli version" in result.output


class TestAccountsCommand:
    """Tests for accounts command."""

    @patch("mm_cli.cli.export_accounts")
    def test_accounts_table_format(self, mock_export: MagicMock, sample_accounts) -> None:
        """Test accounts command with table format."""
        mock_export.return_value = sample_accounts

        result = runner.invoke(app, ["accounts"])

        assert result.exit_code == 0
        assert "Girokonto" in result.output
        assert "Commerzbank" in result.output

    @patch("mm_cli.cli.export_accounts")
    def test_accounts_json_format(self, mock_export: MagicMock, sample_accounts) -> None:
        """Test accounts command with JSON format."""
        mock_export.return_value = sample_accounts

        result = runner.invoke(app, ["accounts", "--format", "json"])

        assert result.exit_code == 0
        assert '"name": "Girokonto"' in result.output
        assert '"balance": "1234.56"' in result.output


class TestCategoriesCommand:
    """Tests for categories command."""

    @patch("mm_cli.cli.export_categories")
    def test_categories_table_format(self, mock_export: MagicMock, sample_categories) -> None:
        """Test categories command with table format."""
        mock_export.return_value = sample_categories

        result = runner.invoke(app, ["categories"])

        assert result.exit_code == 0
        assert "Gehalt" in result.output
        assert "Lebensmittel" in result.output


class TestTransactionsCommand:
    """Tests for transactions command."""

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_default(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test transactions command with defaults."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions"])

        assert result.exit_code == 0
        # Rich may wrap text across lines, so check for parts
        assert "Arbeitgeber" in result.output
        assert "REWE" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_uncategorized_filter(
        self, mock_export: MagicMock, sample_transactions
    ) -> None:
        """Test transactions command with uncategorized filter."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--uncategorized"])

        assert result.exit_code == 0
        # Only the uncategorized transaction should appear
        assert "Unknown" in result.output
        # Categorized transactions should not appear
        assert "Arbeitgeber" not in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_category_filter(
        self, mock_export: MagicMock, sample_transactions
    ) -> None:
        """Test transactions command with category filter."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--category", "Gehalt"])

        assert result.exit_code == 0
        # Rich may wrap text, so check for parts
        assert "Arbeitgeber" in result.output
        assert "REWE" not in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_date_filter(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test transactions command with date filters."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--from", "2024-01-01", "--to", "2024-12-31"])

        assert result.exit_code == 0
        mock_export.assert_called_once()

    def test_transactions_invalid_date(self) -> None:
        """Test transactions command with invalid date format."""
        result = runner.invoke(app, ["transactions", "--from", "invalid-date"])

        assert result.exit_code == 1
        assert "Invalid date format" in result.output


class TestTransactionsGroupFilter:
    """Tests for transactions command with --group filter."""

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_transactions")
    def test_transactions_group_filter(
        self, mock_tx: MagicMock, mock_accs: MagicMock,
        sample_transactions, multi_group_accounts,
    ) -> None:
        """Test transactions command filters by account group."""
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2024, 1, 15), value_date=date(2024, 1, 15),
                amount=Decimal("100.00"), currency="EUR",
                name="PrivatPay", purpose="test",
            ),
            Transaction(
                id="2", account_id="uuid-cognovis-giro",
                booking_date=date(2024, 1, 16), value_date=date(2024, 1, 16),
                amount=Decimal("200.00"), currency="EUR",
                name="BizPay", purpose="test",
            ),
        ]
        mock_accs.return_value = multi_group_accounts

        result = runner.invoke(app, ["transactions", "--group", "Privat"])

        assert result.exit_code == 0
        assert "PrivatPay" in result.output
        assert "BizPay" not in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_transactions")
    def test_transactions_group_filter_case_insensitive(
        self, mock_tx: MagicMock, mock_accs: MagicMock,
        multi_group_accounts,
    ) -> None:
        """Test transactions --group is case-insensitive."""
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2024, 1, 15), value_date=date(2024, 1, 15),
                amount=Decimal("100.00"), currency="EUR",
                name="PrivatPay", purpose="test",
            ),
        ]
        mock_accs.return_value = multi_group_accounts

        result = runner.invoke(app, ["transactions", "--group", "privat"])

        assert result.exit_code == 0
        assert "PrivatPay" in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_transactions")
    def test_transactions_group_filter_multiple(
        self, mock_tx: MagicMock, mock_accs: MagicMock,
        multi_group_accounts,
    ) -> None:
        """Test transactions with multiple --group values."""
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2024, 1, 15), value_date=date(2024, 1, 15),
                amount=Decimal("100.00"), currency="EUR",
                name="PrivatPay", purpose="test",
            ),
            Transaction(
                id="2", account_id="uuid-cognovis-giro",
                booking_date=date(2024, 1, 16), value_date=date(2024, 1, 16),
                amount=Decimal("200.00"), currency="EUR",
                name="BizPay", purpose="test",
            ),
        ]
        mock_accs.return_value = multi_group_accounts

        result = runner.invoke(
            app, ["transactions", "--group", "Privat", "--group", "cognovis"],
        )

        assert result.exit_code == 0
        assert "PrivatPay" in result.output
        assert "BizPay" in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_transactions")
    def test_transactions_group_filter_no_match(
        self, mock_tx: MagicMock, mock_accs: MagicMock,
        multi_group_accounts,
    ) -> None:
        """Test transactions --group with no matching accounts."""
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="uuid-privat-giro",
                booking_date=date(2024, 1, 15), value_date=date(2024, 1, 15),
                amount=Decimal("100.00"), currency="EUR",
                name="PrivatPay", purpose="test",
            ),
        ]
        mock_accs.return_value = multi_group_accounts

        result = runner.invoke(app, ["transactions", "--group", "NonExistent"])

        assert result.exit_code == 0
        assert "No transactions found" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_without_group_no_account_fetch(
        self, mock_tx: MagicMock, sample_transactions,
    ) -> None:
        """Test that accounts are NOT fetched when --group is not used."""
        mock_tx.return_value = sample_transactions

        with patch("mm_cli.cli.export_accounts") as mock_accs:
            result = runner.invoke(app, ["transactions"])

            assert result.exit_code == 0
            mock_accs.assert_not_called()


class TestTransactionsAmountFilter:
    """Tests for transactions command with --min-amount and --max-amount."""

    @patch("mm_cli.cli.export_transactions")
    def test_min_amount_filter(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --min-amount filters out smaller transactions."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--min-amount", "100"])

        assert result.exit_code == 0
        # Only the salary (3500.00) should remain
        assert "Arbeitgeber" in result.output
        assert "REWE" not in result.output
        assert "Unknown" not in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_max_amount_filter(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --max-amount filters out larger transactions."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--max-amount", "50"])

        assert result.exit_code == 0
        # REWE (45.50) and Unknown (12.99) should remain, not salary (3500)
        assert "REWE" in result.output
        assert "Unknown" in result.output
        assert "Arbeitgeber" not in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_min_and_max_amount_combined(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --min-amount and --max-amount combined."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--min-amount", "20", "--max-amount", "100"])

        assert result.exit_code == 0
        # Only REWE (45.50) should remain
        assert "REWE" in result.output
        assert "Arbeitgeber" not in result.output
        assert "Unknown" not in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_min_amount_no_match(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --min-amount with no matching transactions."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--min-amount", "10000"])

        assert result.exit_code == 0
        assert "No transactions found" in result.output


class TestTransactionsSorting:
    """Tests for transactions command with --sort and --reverse."""

    @patch("mm_cli.cli.export_transactions")
    def test_sort_by_date(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --sort date produces ascending date order."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--sort", "date", "--format", "json"])

        assert result.exit_code == 0
        # Verify order: 2024-01-15, 2024-01-16, 2024-01-17
        output = result.output
        pos_arbeitgeber = output.index("Arbeitgeber")
        pos_rewe = output.index("REWE")
        pos_unknown = output.index("Unknown")
        assert pos_arbeitgeber < pos_rewe < pos_unknown

    @patch("mm_cli.cli.export_transactions")
    def test_sort_by_amount(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --sort amount produces biggest-first order by default."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--sort", "amount", "--format", "json"])

        assert result.exit_code == 0
        # Default: biggest first -> Arbeitgeber (3500), REWE (45.50), Unknown (12.99)
        output = result.output
        pos_arbeitgeber = output.index("Arbeitgeber")
        pos_rewe = output.index("REWE")
        pos_unknown = output.index("Unknown")
        assert pos_arbeitgeber < pos_rewe < pos_unknown

    @patch("mm_cli.cli.export_transactions")
    def test_sort_by_name(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --sort name produces alphabetical order."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--sort", "name", "--format", "json"])

        assert result.exit_code == 0
        # Alphabetical: Arbeitgeber, REWE, Unknown
        output = result.output
        pos_arbeitgeber = output.index("Arbeitgeber")
        pos_rewe = output.index("REWE")
        pos_unknown = output.index("Unknown")
        assert pos_arbeitgeber < pos_rewe < pos_unknown

    @patch("mm_cli.cli.export_transactions")
    def test_reverse_flag(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --reverse reverses default order."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--reverse", "--format", "json"])

        assert result.exit_code == 0
        # Original order reversed: Unknown first, then REWE, then Arbeitgeber
        output = result.output
        pos_unknown = output.index("Unknown")
        pos_rewe = output.index("REWE")
        pos_arbeitgeber = output.index("Arbeitgeber")
        assert pos_unknown < pos_rewe < pos_arbeitgeber

    @patch("mm_cli.cli.export_transactions")
    def test_sort_amount_with_reverse(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --sort amount --reverse produces smallest-first order."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(
            app, ["transactions", "--sort", "amount", "--reverse", "--format", "json"],
        )

        assert result.exit_code == 0
        # Reversed: smallest first -> Unknown (12.99), REWE (45.50), Arbeitgeber (3500)
        output = result.output
        pos_unknown = output.index("Unknown")
        pos_rewe = output.index("REWE")
        pos_arbeitgeber = output.index("Arbeitgeber")
        assert pos_unknown < pos_rewe < pos_arbeitgeber

    def test_sort_invalid_value(self) -> None:
        """Test --sort with invalid value shows error."""
        result = runner.invoke(app, ["transactions", "--sort", "invalid"])

        assert result.exit_code == 1
        assert "Invalid sort field" in result.output


class TestTransactionsCheckmarkFilter:
    """Tests for transactions command with --checkmark filter."""

    @patch("mm_cli.cli.export_transactions")
    def test_checkmark_on(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --checkmark on shows only checked transactions."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--checkmark", "on"])

        assert result.exit_code == 0
        # Only Arbeitgeber has checkmark=True
        assert "Arbeitgeber" in result.output
        assert "REWE" not in result.output
        assert "Unknown" not in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_checkmark_off(self, mock_export: MagicMock, sample_transactions) -> None:
        """Test --checkmark off shows only unchecked transactions."""
        mock_export.return_value = sample_transactions

        result = runner.invoke(app, ["transactions", "--checkmark", "off"])

        assert result.exit_code == 0
        # REWE and Unknown have checkmark=False
        assert "REWE" in result.output
        assert "Unknown" in result.output
        assert "Arbeitgeber" not in result.output

    def test_checkmark_invalid_value(self) -> None:
        """Test --checkmark with invalid value shows error."""
        result = runner.invoke(app, ["transactions", "--checkmark", "maybe"])

        assert result.exit_code == 1
        assert "Invalid checkmark value" in result.output


class TestCategoryUsageCommand:
    """Tests for category-usage command."""

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_category_usage(
        self,
        mock_tx: MagicMock,
        mock_cat: MagicMock,
        sample_transactions,
        sample_categories,
    ) -> None:
        """Test category-usage command."""
        mock_tx.return_value = sample_transactions
        mock_cat.return_value = sample_categories

        result = runner.invoke(app, ["category-usage"])

        assert result.exit_code == 0
        assert "Category Usage" in result.output


class TestSetCategoryCommand:
    """Tests for set-category command."""

    @patch("mm_cli.cli.find_category_by_name")
    @patch("mm_cli.cli.set_transaction_category")
    def test_set_category_by_name(
        self,
        mock_set: MagicMock,
        mock_find: MagicMock,
        sample_categories,
    ) -> None:
        """Test set-category command with category name."""
        mock_find.return_value = sample_categories[1]  # Gehalt
        mock_set.return_value = True

        result = runner.invoke(app, ["set-category", "12345", "Gehalt"])

        assert result.exit_code == 0
        assert "category set to" in result.output
        mock_set.assert_called_once()

    @patch("mm_cli.cli.find_category_by_name")
    def test_set_category_dry_run(
        self,
        mock_find: MagicMock,
        sample_categories,
    ) -> None:
        """Test set-category command with --dry-run."""
        mock_find.return_value = sample_categories[1]  # Gehalt

        result = runner.invoke(app, ["set-category", "12345", "Gehalt", "--dry-run"])

        assert result.exit_code == 0
        assert "Would set" in result.output

    @patch("mm_cli.cli.find_category_by_name")
    def test_set_category_not_found(self, mock_find: MagicMock) -> None:
        """Test set-category command with non-existent category."""
        mock_find.return_value = None

        result = runner.invoke(app, ["set-category", "12345", "NonExistent"])

        assert result.exit_code == 1
        assert "Category not found" in result.output


class TestSetCheckmarkCommand:
    """Tests for set-checkmark command."""

    @patch("mm_cli.cli.set_transaction_checkmark")
    def test_set_checkmark_on(self, mock_set: MagicMock) -> None:
        """Test set-checkmark on calls applescript with checked=True."""
        mock_set.return_value = True

        result = runner.invoke(app, ["set-checkmark", "12345", "on"])

        assert result.exit_code == 0
        assert "checkmark set to: on" in result.output
        mock_set.assert_called_once_with("12345", checked=True)

    @patch("mm_cli.cli.set_transaction_checkmark")
    def test_set_checkmark_off(self, mock_set: MagicMock) -> None:
        """Test set-checkmark off calls applescript with checked=False."""
        mock_set.return_value = True

        result = runner.invoke(app, ["set-checkmark", "12345", "off"])

        assert result.exit_code == 0
        assert "checkmark set to: off" in result.output
        mock_set.assert_called_once_with("12345", checked=False)

    def test_set_checkmark_invalid_state(self) -> None:
        """Test set-checkmark with invalid state shows error."""
        result = runner.invoke(app, ["set-checkmark", "12345", "maybe"])

        assert result.exit_code == 1
        assert "Invalid state" in result.output


class TestSetCommentCommand:
    """Tests for set-comment command."""

    @patch("mm_cli.cli.set_transaction_comment")
    def test_set_comment(self, mock_set: MagicMock) -> None:
        """Test set-comment calls applescript with comment text."""
        mock_set.return_value = True

        result = runner.invoke(app, ["set-comment", "12345", "Reviewed and approved"])

        assert result.exit_code == 0
        assert "comment set to: Reviewed and approved" in result.output
        mock_set.assert_called_once_with("12345", "Reviewed and approved")

    @patch("mm_cli.cli.set_transaction_comment")
    def test_set_comment_empty_clears(self, mock_set: MagicMock) -> None:
        """Test set-comment with empty string clears the comment."""
        mock_set.return_value = True

        result = runner.invoke(app, ["set-comment", "12345", ""])

        assert result.exit_code == 0
        assert "comment cleared" in result.output
        mock_set.assert_called_once_with("12345", "")


class TestAccountsFilters:
    """Tests for accounts command with new filter flags."""

    @patch("mm_cli.cli.export_accounts")
    def test_accounts_active_filter(self, mock_export: MagicMock) -> None:
        """Test accounts command with --active flag filters out Aufgelöst group."""
        mock_export.return_value = [
            Account(
                id="1", name="Girokonto", account_number="123",
                bank_name="Bank", balance=Decimal("1000"), group="Hauptkonten",
            ),
            Account(
                id="2", name="Altes Konto", account_number="456",
                bank_name="Bank", balance=Decimal("0"), group="Aufgelöst",
            ),
        ]

        result = runner.invoke(app, ["accounts", "--active"])

        assert result.exit_code == 0
        assert "Girokonto" in result.output
        assert "Altes Konto" not in result.output

    @patch("mm_cli.cli.export_accounts")
    def test_accounts_group_filter(self, mock_export: MagicMock) -> None:
        """Test accounts command with --group flag."""
        mock_export.return_value = [
            Account(
                id="1", name="Girokonto", account_number="123",
                bank_name="Bank", balance=Decimal("1000"), group="Privat",
            ),
            Account(
                id="2", name="Firmenkonto", account_number="456",
                bank_name="Bank", balance=Decimal("5000"), group="Business",
            ),
        ]

        result = runner.invoke(app, ["accounts", "--group", "Privat"])

        assert result.exit_code == 0
        assert "Girokonto" in result.output
        assert "Firmenkonto" not in result.output

    @patch("mm_cli.cli.export_accounts")
    def test_accounts_hierarchy_mode(self, mock_export: MagicMock) -> None:
        """Test accounts command with --hierarchy flag."""
        mock_export.return_value = [
            Account(
                id="1", name="Girokonto", account_number="123",
                bank_name="Bank", balance=Decimal("1000"), group="Hauptkonten",
            ),
            Account(
                id="2", name="Tagesgeld", account_number="456",
                bank_name="Bank", balance=Decimal("5000"), group="Sparkonten",
            ),
        ]

        result = runner.invoke(app, ["accounts", "--hierarchy"])

        assert result.exit_code == 0
        assert "Hauptkonten" in result.output
        assert "Sparkonten" in result.output
        assert "Subtotal" in result.output

    @patch("mm_cli.cli.export_accounts")
    def test_accounts_group_column_in_json(self, mock_export: MagicMock) -> None:
        """Test that group field appears in JSON output."""
        mock_export.return_value = [
            Account(
                id="1", name="Girokonto", account_number="123",
                bank_name="Bank", balance=Decimal("1000"), group="Privat",
            ),
        ]

        result = runner.invoke(app, ["accounts", "--format", "json"])

        assert result.exit_code == 0
        assert '"group": "Privat"' in result.output


class TestAnalyzeSpending:
    """Tests for analyze spending command."""

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_default(
        self, mock_tx: MagicMock, mock_cat: MagicMock, mock_accs: MagicMock,
    ) -> None:
        """Test analyze spending with defaults."""
        mock_accs.return_value = []
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-45.00"),
                currency="EUR", name="REWE", purpose="Einkauf",
                category_id="cat1", category_name="Lebensmittel",
            ),
        ]
        mock_cat.return_value = [
            Category(
                id="cat1", name="Lebensmittel",
                category_type=CategoryType.EXPENSE,
                budget=Decimal("500"), budget_period="monthly",
            ),
        ]

        result = runner.invoke(app, ["analyze", "spending"])

        assert result.exit_code == 0
        assert "Spending Analysis" in result.output
        assert "Lebensmittel" in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_type_filter(
        self, mock_tx: MagicMock, mock_cat: MagicMock, mock_accs: MagicMock,
    ) -> None:
        """Test analyze spending with --type expense."""
        mock_accs.return_value = []
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-45.00"),
                currency="EUR", name="REWE", purpose="Einkauf",
                category_id="cat1", category_name="Lebensmittel",
            ),
            Transaction(
                id="2", account_id="acc1", booking_date=date(2026, 1, 15),
                value_date=date(2026, 1, 15), amount=Decimal("3500.00"),
                currency="EUR", name="Gehalt", purpose="Lohn",
                category_id="cat2", category_name="Gehalt",
            ),
        ]
        mock_cat.return_value = []

        result = runner.invoke(app, ["analyze", "spending", "--type", "expense"])

        assert result.exit_code == 0
        assert "Lebensmittel" in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_json_format(
        self, mock_tx: MagicMock, mock_cat: MagicMock, mock_accs: MagicMock,
    ) -> None:
        """Test analyze spending with JSON output."""
        mock_accs.return_value = []
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-45.00"),
                currency="EUR", name="REWE", purpose="Einkauf",
                category_id="cat1", category_name="Lebensmittel",
            ),
        ]
        mock_cat.return_value = []

        result = runner.invoke(app, ["analyze", "spending", "--format", "json"])

        assert result.exit_code == 0
        assert '"category_name": "Lebensmittel"' in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_explicit_dates(
        self, mock_tx: MagicMock, mock_cat: MagicMock, mock_accs: MagicMock,
    ) -> None:
        """Test analyze spending with explicit --from and --to."""
        mock_accs.return_value = []
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-45.00"),
                currency="EUR", name="REWE", purpose="Einkauf",
                category_id="cat1", category_name="Lebensmittel",
            ),
        ]
        mock_cat.return_value = []

        result = runner.invoke(app, [
            "analyze", "spending",
            "--from", "2026-01-01", "--to", "2026-01-31",
        ])

        assert result.exit_code == 0

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_no_transactions(
        self, mock_tx: MagicMock, mock_cat: MagicMock, mock_accs: MagicMock,
    ) -> None:
        """Test analyze spending with no matching transactions."""
        mock_accs.return_value = []
        mock_tx.return_value = []
        mock_cat.return_value = []

        result = runner.invoke(app, ["analyze", "spending"])

        assert result.exit_code == 0
        assert "No transactions" in result.output


class TestAnalyzeCashflow:
    """Tests for analyze cashflow command."""

    @patch("mm_cli.analysis.date")
    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_cashflow_default(
        self, mock_tx, mock_cat, mock_accs, mock_cli_date, mock_analysis_date,
        rich_transactions, transfer_categories,
    ) -> None:
        for md in (mock_cli_date, mock_analysis_date):
            md.today.return_value = date(2025, 6, 15)
            md.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "cashflow"])

        assert result.exit_code == 0
        assert "Cashflow" in result.output

    @patch("mm_cli.analysis.date")
    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_cashflow_quarterly(
        self, mock_tx, mock_cat, mock_accs, mock_cli_date, mock_analysis_date,
        rich_transactions, transfer_categories,
    ) -> None:
        for md in (mock_cli_date, mock_analysis_date):
            md.today.return_value = date(2025, 6, 15)
            md.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "cashflow", "--period", "quarterly"])

        assert result.exit_code == 0

    @patch("mm_cli.analysis.date")
    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_cashflow_json(
        self, mock_tx, mock_cat, mock_accs, mock_cli_date, mock_analysis_date,
        rich_transactions, transfer_categories,
    ) -> None:
        for md in (mock_cli_date, mock_analysis_date):
            md.today.return_value = date(2025, 6, 15)
            md.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "cashflow", "--format", "json"])

        assert result.exit_code == 0
        assert '"period_label"' in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_cashflow_no_transactions(
        self, mock_tx, mock_cat, mock_accs, transfer_categories,
    ) -> None:
        mock_tx.return_value = []
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "cashflow"])

        assert result.exit_code == 0
        assert "No transactions" in result.output

    @patch("mm_cli.analysis.date")
    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_transactions")
    def test_cashflow_with_group(
        self, mock_tx, mock_accs, mock_cat,
        mock_cli_date, mock_analysis_date,
        rich_transactions, sample_accounts, transfer_categories,
    ) -> None:
        for md in (mock_cli_date, mock_analysis_date):
            md.today.return_value = date(2025, 6, 15)
            md.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = rich_transactions
        mock_accs.return_value = sample_accounts
        mock_cat.return_value = transfer_categories

        result = runner.invoke(app, ["analyze", "cashflow", "--group", "Hauptkonten"])

        assert result.exit_code == 0

    @patch("mm_cli.analysis.date")
    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_transactions")
    def test_cashflow_include_transfers(
        self, mock_tx, mock_cli_date, mock_analysis_date,
        rich_transactions,
    ) -> None:
        """With --include-transfers, categories are not loaded."""
        for md in (mock_cli_date, mock_analysis_date):
            md.today.return_value = date(2025, 6, 15)
            md.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = rich_transactions

        result = runner.invoke(
            app, ["analyze", "cashflow", "--include-transfers"],
        )

        assert result.exit_code == 0
        assert "Cashflow" in result.output


class TestAnalyzeRecurring:
    """Tests for analyze recurring command."""

    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_recurring_default(
        self, mock_tx, mock_cat, mock_accs, mock_cli_date,
        rich_transactions, transfer_categories,
    ) -> None:
        mock_cli_date.today.return_value = date(2025, 6, 15)
        mock_cli_date.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "recurring"])

        assert result.exit_code == 0
        assert "Recurring" in result.output

    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_recurring_json(
        self, mock_tx, mock_cat, mock_accs, mock_cli_date,
        rich_transactions, transfer_categories,
    ) -> None:
        mock_cli_date.today.return_value = date(2025, 6, 15)
        mock_cli_date.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "recurring", "--format", "json"])

        assert result.exit_code == 0
        assert '"merchant_name"' in result.output

    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_recurring_no_transactions(
        self, mock_tx, mock_cat, mock_accs, mock_cli_date, transfer_categories,
    ) -> None:
        mock_cli_date.today.return_value = date(2025, 6, 15)
        mock_cli_date.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = []
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "recurring"])

        assert result.exit_code == 0
        assert "No transactions" in result.output

    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_recurring_high_threshold(
        self, mock_tx, mock_cat, mock_accs, mock_cli_date,
        rich_transactions, transfer_categories,
    ) -> None:
        mock_cli_date.today.return_value = date(2025, 6, 15)
        mock_cli_date.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(
            app, ["analyze", "recurring", "--min-occurrences", "100"],
        )

        assert result.exit_code == 0
        assert "No recurring" in result.output


class TestAnalyzeMerchants:
    """Tests for analyze merchants command."""

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_merchants_default(
        self, mock_tx, mock_cat, mock_accs, rich_transactions, transfer_categories,
    ) -> None:
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "merchants"])

        assert result.exit_code == 0
        assert "Merchant" in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_merchants_type_all(
        self, mock_tx, mock_cat, mock_accs, rich_transactions, transfer_categories,
    ) -> None:
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(
            app, ["analyze", "merchants", "--type", "all"],
        )

        assert result.exit_code == 0

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_merchants_json(
        self, mock_tx, mock_cat, mock_accs, rich_transactions, transfer_categories,
    ) -> None:
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "merchants", "--format", "json"])

        assert result.exit_code == 0
        assert '"merchant_name"' in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_merchants_with_limit(
        self, mock_tx, mock_cat, mock_accs, rich_transactions, transfer_categories,
    ) -> None:
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "merchants", "--limit", "2"])

        assert result.exit_code == 0

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_merchants_no_transactions(
        self, mock_tx, mock_cat, mock_accs, transfer_categories,
    ) -> None:
        mock_tx.return_value = []
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "merchants"])

        assert result.exit_code == 0
        assert "No transactions" in result.output


class TestAnalyzeTopCustomers:
    """Tests for analyze top-customers command."""

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_top_customers_default(
        self, mock_tx, mock_cat, mock_accs, rich_transactions, transfer_categories,
    ) -> None:
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "top-customers"])

        assert result.exit_code == 0
        assert "Customer" in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_top_customers_json(
        self, mock_tx, mock_cat, mock_accs, rich_transactions, transfer_categories,
    ) -> None:
        mock_tx.return_value = rich_transactions
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(
            app, ["analyze", "top-customers", "--format", "json"],
        )

        assert result.exit_code == 0
        assert '"merchant_name"' in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_top_customers_no_transactions(
        self, mock_tx, mock_cat, mock_accs, transfer_categories,
    ) -> None:
        mock_tx.return_value = []
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "top-customers"])

        assert result.exit_code == 0
        assert "No transactions" in result.output

    @patch("mm_cli.cli.export_accounts")
    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_top_customers_only_expenses(
        self, mock_tx, mock_cat, mock_accs, transfer_categories,
    ) -> None:
        """When all transactions are expenses, no customers found."""
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2025, 1, 5),
                value_date=date(2025, 1, 5), amount=Decimal("-50.00"),
                currency="EUR", name="Shop", purpose="",
            ),
        ]
        mock_cat.return_value = transfer_categories
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "top-customers"])

        assert result.exit_code == 0
        assert "No income" in result.output


class TestAnalyzeBalanceHistory:
    """Tests for analyze balance-history command."""

    @patch("mm_cli.analysis.date")
    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_transactions")
    @patch("mm_cli.cli.export_accounts")
    def test_balance_history_default(
        self, mock_accs: MagicMock, mock_tx: MagicMock,
        mock_cli_date: MagicMock, mock_analysis_date: MagicMock,
        sample_accounts, rich_transactions,
    ) -> None:
        for md in (mock_cli_date, mock_analysis_date):
            md.today.return_value = date(2025, 6, 15)
            md.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_accs.return_value = sample_accounts
        mock_tx.return_value = rich_transactions

        result = runner.invoke(app, ["analyze", "balance-history"])

        assert result.exit_code == 0
        assert "Balance" in result.output

    @patch("mm_cli.analysis.date")
    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_transactions")
    @patch("mm_cli.cli.export_accounts")
    def test_balance_history_json(
        self, mock_accs: MagicMock, mock_tx: MagicMock,
        mock_cli_date: MagicMock, mock_analysis_date: MagicMock,
        sample_accounts, rich_transactions,
    ) -> None:
        for md in (mock_cli_date, mock_analysis_date):
            md.today.return_value = date(2025, 6, 15)
            md.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_accs.return_value = sample_accounts
        mock_tx.return_value = rich_transactions

        result = runner.invoke(app, ["analyze", "balance-history", "--format", "json"])

        assert result.exit_code == 0
        assert '"period_label"' in result.output

    @patch("mm_cli.analysis.date")
    @patch("mm_cli.cli.date")
    @patch("mm_cli.cli.export_transactions")
    @patch("mm_cli.cli.export_accounts")
    def test_balance_history_single_account(
        self, mock_accs: MagicMock, mock_tx: MagicMock,
        mock_cli_date: MagicMock, mock_analysis_date: MagicMock,
        sample_accounts, rich_transactions,
    ) -> None:
        for md in (mock_cli_date, mock_analysis_date):
            md.today.return_value = date(2025, 6, 15)
            md.side_effect = lambda *args, **kw: date(*args, **kw)
        mock_accs.return_value = sample_accounts
        mock_tx.return_value = rich_transactions

        result = runner.invoke(app, ["analyze", "balance-history", "--account", "Girokonto"])

        assert result.exit_code == 0

    @patch("mm_cli.cli.export_accounts")
    def test_balance_history_no_accounts(self, mock_accs: MagicMock) -> None:
        mock_accs.return_value = []

        result = runner.invoke(app, ["analyze", "balance-history", "--account", "NonExistent"])

        assert result.exit_code == 0
        assert "No accounts" in result.output


class TestTransferCommand:
    """Tests for the transfer command."""

    @patch("mm_cli.cli.export_accounts")
    def test_transfer_dry_run(self, mock_accs: MagicMock, sample_accounts) -> None:
        """Test dry-run mode shows summary but doesn't execute."""
        mock_accs.return_value = sample_accounts

        result = runner.invoke(app, [
            "transfer",
            "--from-account", "Girokonto",
            "--to", "Max Mustermann",
            "--iban", "DE89370400440532013000",
            "--amount", "100.00",
            "--purpose", "Test transfer",
            "--dry-run",
        ])

        assert result.exit_code == 0
        assert "Transfer Summary" in result.output
        assert "Max Mustermann" in result.output
        assert "100.00" in result.output
        assert "Test transfer" in result.output
        assert "Dry run" in result.output

    def test_transfer_invalid_iban(self) -> None:
        """Test invalid IBAN is rejected."""
        result = runner.invoke(app, [
            "transfer",
            "--from-account", "Girokonto",
            "--to", "Max Mustermann",
            "--iban", "INVALID",
            "--amount", "100.00",
            "--purpose", "Test transfer",
            "--confirm",
        ])

        assert result.exit_code == 1
        assert "Invalid IBAN" in result.output

    @patch("mm_cli.cli.create_bank_transfer")
    @patch("mm_cli.cli.export_accounts")
    def test_transfer_with_confirm(
        self, mock_accs: MagicMock, mock_transfer: MagicMock, sample_accounts,
    ) -> None:
        """Test transfer execution with --confirm flag."""
        mock_accs.return_value = sample_accounts
        mock_transfer.return_value = ""

        result = runner.invoke(app, [
            "transfer",
            "--from-account", "Girokonto",
            "--to", "Max Mustermann",
            "--iban", "DE89370400440532013000",
            "--amount", "100.00",
            "--purpose", "Test transfer",
            "--confirm",
        ])

        assert result.exit_code == 0
        assert "initiated successfully" in result.output
        mock_transfer.assert_called_once_with(
            account_number="DE89370400440532013000",
            recipient="Max Mustermann",
            iban="DE89370400440532013000",
            amount=100.00,
            purpose="Test transfer",
            outbox=False,
        )

    @patch("mm_cli.cli.export_accounts")
    def test_transfer_account_not_found(self, mock_accs: MagicMock) -> None:
        """Test account lookup failure shows error."""
        mock_accs.return_value = []

        result = runner.invoke(app, [
            "transfer",
            "--from-account", "NonExistent",
            "--to", "Max Mustermann",
            "--iban", "DE89370400440532013000",
            "--amount", "100.00",
            "--purpose", "Test transfer",
            "--confirm",
        ])

        assert result.exit_code == 1
        assert "Account not found" in result.output

    def test_transfer_negative_amount(self) -> None:
        """Test negative amount is rejected."""
        result = runner.invoke(app, [
            "transfer",
            "--from-account", "Girokonto",
            "--to", "Max Mustermann",
            "--iban", "DE89370400440532013000",
            "--amount", "-50.00",
            "--purpose", "Test",
            "--confirm",
        ])

        assert result.exit_code == 1
        assert "Amount must be positive" in result.output

    @patch("mm_cli.cli.create_bank_transfer")
    @patch("mm_cli.cli.export_accounts")
    def test_transfer_with_outbox(
        self, mock_accs: MagicMock, mock_transfer: MagicMock, sample_accounts,
    ) -> None:
        """Test transfer with --outbox flag."""
        mock_accs.return_value = sample_accounts
        mock_transfer.return_value = ""

        result = runner.invoke(app, [
            "transfer",
            "--from-account", "Girokonto",
            "--to", "Max Mustermann",
            "--iban", "DE89370400440532013000",
            "--amount", "250.00",
            "--purpose", "Invoice payment",
            "--confirm",
            "--outbox",
        ])

        assert result.exit_code == 0
        mock_transfer.assert_called_once_with(
            account_number="DE89370400440532013000",
            recipient="Max Mustermann",
            iban="DE89370400440532013000",
            amount=250.00,
            purpose="Invoice payment",
            outbox=True,
        )

    @patch("mm_cli.cli.export_accounts")
    def test_transfer_iban_with_spaces(
        self, mock_accs: MagicMock, sample_accounts,
    ) -> None:
        """Test IBAN with spaces is normalized in dry-run."""
        mock_accs.return_value = sample_accounts

        result = runner.invoke(app, [
            "transfer",
            "--from-account", "Girokonto",
            "--to", "Max Mustermann",
            "--iban", "DE89 3704 0044 0532 0130 00",
            "--amount", "100.00",
            "--purpose", "Test",
            "--dry-run",
        ])

        assert result.exit_code == 0
        assert "DE89370400440532013000" in result.output

    @patch("mm_cli.cli.export_accounts")
    def test_transfer_lookup_by_iban(
        self, mock_accs: MagicMock, sample_accounts,
    ) -> None:
        """Test account lookup by IBAN."""
        mock_accs.return_value = sample_accounts

        result = runner.invoke(app, [
            "transfer",
            "--from-account", "DE89370400440532013000",
            "--to", "Max Mustermann",
            "--iban", "DE27100777770209299700",
            "--amount", "50.00",
            "--purpose", "Test",
            "--dry-run",
        ])

        assert result.exit_code == 0
        assert "Girokonto" in result.output


class TestPortfolioCommand:
    """Tests for portfolio command."""

    @patch("mm_cli.cli.export_portfolio")
    def test_portfolio_table_format(self, mock_export: MagicMock, sample_portfolios) -> None:
        """Test portfolio command with table format."""
        mock_export.return_value = sample_portfolios

        result = runner.invoke(app, ["portfolio"])

        assert result.exit_code == 0
        assert "Portfolio" in result.output
        # Rich may wrap text across lines, so check for parts
        assert "iShares" in result.output
        assert "Xtrackers" in result.output

    @patch("mm_cli.cli.export_portfolio")
    def test_portfolio_json_format(self, mock_export: MagicMock, sample_portfolios) -> None:
        """Test portfolio command with JSON output."""
        mock_export.return_value = sample_portfolios

        result = runner.invoke(app, ["portfolio", "--format", "json"])

        assert result.exit_code == 0
        assert '"name": "iShares Core MSCI World"' in result.output
        assert '"isin": "IE00B4L5Y983"' in result.output
        assert '"market_value": 3925.0' in result.output

    @patch("mm_cli.cli.export_portfolio")
    def test_portfolio_account_filter(self, mock_export: MagicMock, sample_portfolios) -> None:
        """Test portfolio command with account filter."""
        from mm_cli.models import Portfolio

        mock_export.return_value = sample_portfolios + [
            Portfolio(
                account_name="Other Depot",
                account_id="other-uuid",
                securities=[],
                total_value=0.0,
                total_gain_loss=0.0,
            ),
        ]

        result = runner.invoke(app, ["portfolio", "--account", "Commerzbank"])

        assert result.exit_code == 0
        assert "iShares" in result.output

    @patch("mm_cli.cli.export_portfolio")
    def test_portfolio_empty(self, mock_export: MagicMock) -> None:
        """Test portfolio command with no data shows warning."""
        mock_export.return_value = []

        result = runner.invoke(app, ["portfolio"])

        assert result.exit_code == 0
        assert "No portfolio data" in result.output

    @patch("mm_cli.cli.export_portfolio")
    def test_portfolio_no_securities(self, mock_export: MagicMock) -> None:
        """Test portfolio command with portfolios but no securities shows warning."""
        from mm_cli.models import Portfolio

        mock_export.return_value = [
            Portfolio(
                account_name="Empty Depot",
                account_id="empty-uuid",
                securities=[],
                total_value=0.0,
                total_gain_loss=0.0,
            ),
        ]

        result = runner.invoke(app, ["portfolio"])

        assert result.exit_code == 0
        assert "No securities found" in result.output

    @patch("mm_cli.cli.export_portfolio")
    def test_portfolio_csv_format(self, mock_export: MagicMock, sample_portfolios) -> None:
        """Test portfolio command with CSV output."""
        mock_export.return_value = sample_portfolios

        result = runner.invoke(app, ["portfolio", "--format", "csv"])

        assert result.exit_code == 0
        assert "isin" in result.output
        assert "IE00B4L5Y983" in result.output


class TestExportCommand:
    """Tests for the export CLI command."""

    @patch("mm_cli.cli.export_transactions")
    def test_export_sta_format(self, mock_export: MagicMock) -> None:
        """Test export command with MT940/STA format."""
        mock_export.return_value = "/tmp/export.sta"

        result = runner.invoke(app, ["export", "--format", "sta"])

        assert result.exit_code == 0
        assert "Exported to temporary file" in result.output
        assert "/tmp/export.sta" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_export_csv_format(self, mock_export: MagicMock) -> None:
        """Test export command with CSV format."""
        mock_export.return_value = "/tmp/export.csv"

        result = runner.invoke(app, ["export", "--format", "csv"])

        assert result.exit_code == 0
        assert "/tmp/export.csv" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_export_ofx_format(self, mock_export: MagicMock) -> None:
        """Test export command with OFX format."""
        mock_export.return_value = "/tmp/export.ofx"

        result = runner.invoke(app, ["export", "--format", "ofx"])

        assert result.exit_code == 0
        assert "/tmp/export.ofx" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_export_with_date_range(self, mock_export: MagicMock) -> None:
        """Test export command with date range."""
        mock_export.return_value = "/tmp/export.sta"

        result = runner.invoke(app, [
            "export",
            "--from", "2024-01-01",
            "--to", "2024-12-31",
            "--format", "sta",
        ])

        assert result.exit_code == 0
        mock_export.assert_called_once_with(
            account_id=None,
            from_date=date(2024, 1, 1),
            to_date=date(2024, 12, 31),
            export_format="sta",
        )

    @patch("mm_cli.cli.export_transactions")
    def test_export_with_account(self, mock_export: MagicMock) -> None:
        """Test export command with account filter."""
        mock_export.return_value = "/tmp/export.sta"

        result = runner.invoke(app, [
            "export",
            "--account", "DE89370400440532013000",
            "--format", "sta",
        ])

        assert result.exit_code == 0
        mock_export.assert_called_once_with(
            account_id="DE89370400440532013000",
            from_date=None,
            to_date=None,
            export_format="sta",
        )

    @patch("shutil.copy")
    @patch("mm_cli.cli.export_transactions")
    def test_export_with_output_path(self, mock_export: MagicMock, mock_copy: MagicMock) -> None:
        """Test export command with --output saves to specified path."""
        mock_export.return_value = "/tmp/export.sta"

        result = runner.invoke(app, [
            "export",
            "--format", "sta",
            "--output", "/tmp/my_export.sta",
        ])

        assert result.exit_code == 0
        assert "Exported to" in result.output
        mock_copy.assert_called_once()

    def test_export_plist_format_rejected(self) -> None:
        """Test that plist format is rejected with helpful message."""
        result = runner.invoke(app, ["export", "--format", "plist"])

        assert result.exit_code == 1
        assert "mm transactions" in result.output

    def test_export_unsupported_format(self) -> None:
        """Test that unsupported format is rejected."""
        result = runner.invoke(app, ["export", "--format", "pdf"])

        assert result.exit_code == 1
        assert "Unsupported format" in result.output

    def test_export_invalid_date(self) -> None:
        """Test export with invalid date format."""
        result = runner.invoke(app, ["export", "--from", "not-a-date"])

        assert result.exit_code == 1
        assert "Invalid date format" in result.output


class TestSuggestRulesCommand:
    """Tests for the suggest-rules CLI command."""

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_suggest_rules_with_suggestions(
        self, mock_tx: MagicMock, mock_cat: MagicMock,
        sample_categories,
    ) -> None:
        """Test suggest-rules command outputs rule suggestions."""
        # Uncategorized transactions in target range
        uncategorized_txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-45.00"),
                currency="EUR", name="REWE", purpose="REWE SAGT DANKE",
                category_id=None, category_name=None,
            ),
        ]
        # Historical categorized transactions
        categorized_txs = [
            Transaction(
                id="2", account_id="acc1", booking_date=date(2025, 10, 5),
                value_date=date(2025, 10, 5), amount=Decimal("-55.00"),
                currency="EUR", name="REWE", purpose="REWE SAGT DANKE",
                category_id="550e8400-e29b-41d4-a716-446655440003",
                category_name="Lebensmittel",
            ),
            Transaction(
                id="3", account_id="acc1", booking_date=date(2025, 11, 5),
                value_date=date(2025, 11, 5), amount=Decimal("-35.00"),
                currency="EUR", name="REWE", purpose="REWE SAGT DANKE",
                category_id="550e8400-e29b-41d4-a716-446655440003",
                category_name="Lebensmittel",
            ),
        ]
        # First call: target range transactions, second call: all historical
        mock_tx.side_effect = [uncategorized_txs, uncategorized_txs + categorized_txs]
        mock_cat.return_value = sample_categories

        result = runner.invoke(app, [
            "suggest-rules",
            "--from", "2026-01-01", "--to", "2026-01-31",
        ])

        assert result.exit_code == 0
        assert "REWE" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_suggest_rules_no_uncategorized(self, mock_tx: MagicMock) -> None:
        """Test suggest-rules when all transactions are categorized."""
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-45.00"),
                currency="EUR", name="REWE", purpose="test",
                category_id="cat1", category_name="Lebensmittel",
            ),
        ]

        result = runner.invoke(app, [
            "suggest-rules",
            "--from", "2026-01-01", "--to", "2026-01-31",
        ])

        assert result.exit_code == 0
        assert "No uncategorized" in result.output

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_suggest_rules_json_format(
        self, mock_tx: MagicMock, mock_cat: MagicMock,
    ) -> None:
        """Test suggest-rules command with JSON output format."""
        uncategorized_txs = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-45.00"),
                currency="EUR", name="NewShop", purpose="purchase",
                category_id=None, category_name=None,
            ),
        ]
        mock_tx.side_effect = [uncategorized_txs, uncategorized_txs]
        mock_cat.return_value = []

        result = runner.invoke(app, [
            "suggest-rules",
            "--from", "2026-01-01", "--to", "2026-01-31",
            "--format", "json",
        ])

        assert result.exit_code == 0
        assert '"pattern"' in result.output


class TestEdgeCases:
    """Tests for edge cases in CLI commands."""

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_empty_list(self, mock_export: MagicMock) -> None:
        """Test transactions command with empty result."""
        mock_export.return_value = []

        result = runner.invoke(app, ["transactions"])

        assert result.exit_code == 0
        assert "No transactions found" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_null_category_values(self, mock_export: MagicMock) -> None:
        """Test transactions with None category_id and category_name."""
        mock_export.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-25.00"),
                currency="EUR", name="Unknown Shop", purpose="Some purchase",
                category_id=None, category_name=None,
                checkmark=False, comment="",
            ),
        ]

        result = runner.invoke(app, ["transactions"])

        assert result.exit_code == 0
        assert "Unknown Shop" in result.output
        # Should show "uncategorized" placeholder in table (may be truncated by Rich)
        assert "uncategoriz" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_unusual_currency(self, mock_export: MagicMock) -> None:
        """Test transactions with unusual currency (CHF)."""
        mock_export.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("1500.00"),
                currency="CHF", name="SwissPayment", purpose="test",
                category_id=None, category_name=None,
            ),
        ]

        result = runner.invoke(app, ["transactions"])

        assert result.exit_code == 0
        assert "SwissPayment" in result.output
        assert "CHF" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_json_null_categories(self, mock_export: MagicMock) -> None:
        """Test JSON output correctly represents null categories."""
        mock_export.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-10.00"),
                currency="EUR", name="Test", purpose="",
                category_id=None, category_name=None,
            ),
        ]

        result = runner.invoke(app, ["transactions", "--format", "json"])

        assert result.exit_code == 0
        assert '"category_id": null' in result.output
        assert '"category_name": null' in result.output

    @patch("mm_cli.cli.export_accounts")
    def test_accounts_empty_list(self, mock_export: MagicMock) -> None:
        """Test accounts command with empty result."""
        mock_export.return_value = []

        result = runner.invoke(app, ["accounts"])

        assert result.exit_code == 0
        assert "No accounts found" in result.output

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_category_usage_no_categorized_transactions(
        self, mock_tx: MagicMock, mock_cat: MagicMock,
    ) -> None:
        """Test category-usage with no categorized transactions."""
        mock_tx.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-25.00"),
                currency="EUR", name="Shop", purpose="test",
                category_id=None, category_name=None,
            ),
        ]
        mock_cat.return_value = []

        result = runner.invoke(app, ["category-usage"])

        assert result.exit_code == 0
        assert "No categorized" in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_with_long_purpose(self, mock_export: MagicMock) -> None:
        """Test transactions with very long purpose text (truncation)."""
        long_purpose = "A" * 100
        mock_export.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-25.00"),
                currency="EUR", name="Test", purpose=long_purpose,
                category_id=None, category_name=None,
            ),
        ]

        result = runner.invoke(app, ["transactions"])

        assert result.exit_code == 0
        # Purpose should be truncated in table view (Rich uses unicode ellipsis)
        assert "AAAA" in result.output
        # Full 100-char string should NOT appear in the output
        assert long_purpose not in result.output

    @patch("mm_cli.cli.export_transactions")
    def test_transactions_with_empty_counterparty_iban(self, mock_export: MagicMock) -> None:
        """Test transactions with empty counterparty IBAN."""
        mock_export.return_value = [
            Transaction(
                id="1", account_id="acc1", booking_date=date(2026, 1, 5),
                value_date=date(2026, 1, 5), amount=Decimal("-10.00"),
                currency="EUR", name="Cash Withdrawal", purpose="ATM",
                category_id=None, category_name=None,
                counterparty_iban="",
            ),
        ]

        result = runner.invoke(app, ["transactions", "--format", "json"])

        assert result.exit_code == 0
        assert '"counterparty_iban": ""' in result.output
