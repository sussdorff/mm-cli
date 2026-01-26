"""Tests for mm_cli.cli module."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from mm_cli.cli import app
from mm_cli.models import Account, AccountType, Category, CategoryType, Transaction

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

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_default(self, mock_tx: MagicMock, mock_cat: MagicMock) -> None:
        """Test analyze spending with defaults."""
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

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_type_filter(self, mock_tx: MagicMock, mock_cat: MagicMock) -> None:
        """Test analyze spending with --type expense."""
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

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_json_format(self, mock_tx: MagicMock, mock_cat: MagicMock) -> None:
        """Test analyze spending with JSON output."""
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

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_explicit_dates(self, mock_tx: MagicMock, mock_cat: MagicMock) -> None:
        """Test analyze spending with explicit --from and --to."""
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

    @patch("mm_cli.cli.export_categories")
    @patch("mm_cli.cli.export_transactions")
    def test_spending_no_transactions(self, mock_tx: MagicMock, mock_cat: MagicMock) -> None:
        """Test analyze spending with no matching transactions."""
        mock_tx.return_value = []
        mock_cat.return_value = []

        result = runner.invoke(app, ["analyze", "spending"])

        assert result.exit_code == 0
        assert "No transactions" in result.output
