"""Tests for mm_cli.models."""

from decimal import Decimal

from mm_cli.models import (
    Account,
    AccountType,
    Category,
    CategoryType,
    CategoryUsage,
    SpendingAnalysis,
    Transaction,
)


class TestAccount:
    """Tests for Account model."""

    def test_to_dict(self, sample_accounts: list[Account]) -> None:
        """Test Account.to_dict() serialization."""
        account = sample_accounts[0]
        data = account.to_dict()

        assert data["id"] == "DE89370400440532013000"
        assert data["name"] == "Girokonto"
        assert data["balance"] == "1234.56"
        assert data["account_type"] == "checking"
        assert data["iban"] == "DE89370400440532013000"

    def test_account_types(self) -> None:
        """Test AccountType enum values."""
        assert AccountType.CHECKING.value == "checking"
        assert AccountType.SAVINGS.value == "savings"
        assert AccountType.CREDIT_CARD.value == "credit card"


class TestCategory:
    """Tests for Category model."""

    def test_to_dict(self, sample_categories: list[Category]) -> None:
        """Test Category.to_dict() serialization."""
        category = sample_categories[1]  # Gehalt (child category)
        data = category.to_dict()

        assert data["id"] == "550e8400-e29b-41d4-a716-446655440001"
        assert data["name"] == "Gehalt"
        assert data["category_type"] == "income"
        assert data["parent_name"] == "Einkommen"

    def test_category_types(self) -> None:
        """Test CategoryType enum values."""
        assert CategoryType.INCOME.value == "income"
        assert CategoryType.EXPENSE.value == "expense"
        assert CategoryType.TRANSFER.value == "transfer"


class TestTransaction:
    """Tests for Transaction model."""

    def test_to_dict(self, sample_transactions: list[Transaction]) -> None:
        """Test Transaction.to_dict() serialization."""
        tx = sample_transactions[0]
        data = tx.to_dict()

        assert data["id"] == "12345"
        assert data["booking_date"] == "2024-01-15"
        assert data["amount"] == "3500.00"
        assert data["name"] == "Arbeitgeber GmbH"
        assert data["category_name"] == "Gehalt"
        assert data["checkmark"] is True

    def test_uncategorized_transaction(self, sample_transactions: list[Transaction]) -> None:
        """Test uncategorized transaction serialization."""
        tx = sample_transactions[2]  # Uncategorized
        data = tx.to_dict()

        assert data["category_id"] is None
        assert data["category_name"] is None


class TestCategoryUsage:
    """Tests for CategoryUsage model."""

    def test_to_dict(self) -> None:
        """Test CategoryUsage.to_dict() serialization."""
        usage = CategoryUsage(
            category_id="test-uuid",
            category_name="Lebensmittel",
            transaction_count=42,
            total_amount=Decimal("-1234.56"),
            category_type=CategoryType.EXPENSE,
        )
        data = usage.to_dict()

        assert data["category_name"] == "Lebensmittel"
        assert data["transaction_count"] == 42
        assert data["total_amount"] == "-1234.56"
        assert data["category_type"] == "expense"


class TestCategoryBudgetFields:
    """Tests for Category budget_period and budget_available fields."""

    def test_budget_fields_in_to_dict(self) -> None:
        """Test that budget_period and budget_available are serialized."""
        cat = Category(
            id="test",
            name="Food",
            budget=Decimal("500"),
            budget_period="monthly",
            budget_available=Decimal("50"),
        )
        data = cat.to_dict()
        assert data["budget"] == "500"
        assert data["budget_period"] == "monthly"
        assert data["budget_available"] == "50"

    def test_budget_fields_default(self) -> None:
        """Test budget fields default values."""
        cat = Category(id="test", name="Misc")
        assert cat.budget_period == ""
        assert cat.budget_available is None
        data = cat.to_dict()
        assert data["budget_period"] == ""
        assert data["budget_available"] is None


class TestSpendingAnalysis:
    """Tests for SpendingAnalysis model."""

    def test_to_dict_basic(self) -> None:
        """Test SpendingAnalysis.to_dict() serialization."""
        sa = SpendingAnalysis(
            category_name="Lebensmittel",
            category_path="Haushalt\\Lebensmittel",
            category_type=CategoryType.EXPENSE,
            actual=Decimal("-450.00"),
            budget=Decimal("500.00"),
            budget_period="monthly",
            remaining=Decimal("50.00"),
            percent_used=Decimal("90.0"),
            transaction_count=15,
        )
        data = sa.to_dict()

        assert data["category_name"] == "Lebensmittel"
        assert data["actual"] == "-450.00"
        assert data["budget"] == "500.00"
        assert data["remaining"] == "50.00"
        assert data["percent_used"] == "90.0"
        assert data["transaction_count"] == 15
        assert "compare_actual" not in data
        assert "compare_change" not in data

    def test_to_dict_with_comparison(self) -> None:
        """Test SpendingAnalysis with comparison data."""
        sa = SpendingAnalysis(
            category_name="Lebensmittel",
            category_path="Lebensmittel",
            category_type=CategoryType.EXPENSE,
            actual=Decimal("-450.00"),
            budget=None,
            budget_period="",
            remaining=None,
            percent_used=None,
            transaction_count=15,
            compare_actual=Decimal("-400.00"),
            compare_change=Decimal("12.5"),
        )
        data = sa.to_dict()

        assert data["compare_actual"] == "-400.00"
        assert data["compare_change"] == "12.5"
        assert data["budget"] is None
