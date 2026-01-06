"""Data models for MoneyMoney entities."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


class AccountType(Enum):
    """MoneyMoney account types."""

    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT_CARD = "credit card"
    CASH = "cash"
    INVESTMENT = "investment"
    LOAN = "loan"
    OTHER = "other"


class CategoryType(Enum):
    """Category types in MoneyMoney."""

    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


@dataclass
class Account:
    """Represents a MoneyMoney account."""

    id: str
    name: str
    account_number: str
    bank_name: str
    balance: Decimal
    currency: str = "EUR"
    account_type: AccountType = AccountType.OTHER
    owner: str = ""
    iban: str = ""
    bic: str = ""
    group: str = ""
    portfolio: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "account_number": self.account_number,
            "bank_name": self.bank_name,
            "balance": str(self.balance),
            "currency": self.currency,
            "account_type": self.account_type.value,
            "owner": self.owner,
            "iban": self.iban,
            "bic": self.bic,
            "group": self.group,
            "portfolio": self.portfolio,
        }


@dataclass
class Category:
    """Represents a MoneyMoney category."""

    id: str
    name: str
    category_type: CategoryType = CategoryType.EXPENSE
    parent_id: str | None = None
    parent_name: str | None = None
    icon: str = ""
    budget: Decimal | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "category_type": self.category_type.value,
            "parent_id": self.parent_id,
            "parent_name": self.parent_name,
            "icon": self.icon,
            "budget": str(self.budget) if self.budget else None,
        }


@dataclass
class Transaction:
    """Represents a MoneyMoney transaction."""

    id: str
    account_id: str
    booking_date: date
    value_date: date
    amount: Decimal
    currency: str
    name: str
    purpose: str
    category_id: str | None = None
    category_name: str | None = None
    checkmark: bool = False
    comment: str = ""
    account_name: str = ""
    booked: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "booking_date": self.booking_date.isoformat(),
            "value_date": self.value_date.isoformat(),
            "amount": str(self.amount),
            "currency": self.currency,
            "name": self.name,
            "purpose": self.purpose,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "checkmark": self.checkmark,
            "comment": self.comment,
            "booked": self.booked,
        }


@dataclass
class CategoryUsage:
    """Statistics about category usage."""

    category_id: str
    category_name: str
    transaction_count: int
    total_amount: Decimal
    category_type: CategoryType = CategoryType.EXPENSE

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "category_id": self.category_id,
            "category_name": self.category_name,
            "transaction_count": self.transaction_count,
            "total_amount": str(self.total_amount),
            "category_type": self.category_type.value,
        }
