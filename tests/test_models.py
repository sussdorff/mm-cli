"""Tests for mm_cli.models."""

from decimal import Decimal

from mm_cli.models import (
    Account,
    AccountType,
    Category,
    CategoryType,
    CategoryUsage,
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
