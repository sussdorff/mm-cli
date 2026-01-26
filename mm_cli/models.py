"""Data models for MoneyMoney entities."""

from dataclasses import dataclass, field
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
    budget_period: str = ""
    budget_available: Decimal | None = None
    indentation: int = 0
    group: bool = False
    rules: str = ""
    path: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "id": self.id,
            "name": self.name,
            "category_type": self.category_type.value,
            "parent_id": self.parent_id,
            "parent_name": self.parent_name,
            "path": self.path,
            "indentation": self.indentation,
            "group": self.group,
            "budget": str(self.budget) if self.budget else None,
            "budget_period": self.budget_period,
            "budget_available": (
                str(self.budget_available) if self.budget_available is not None else None
            ),
        }
        if self.rules:
            result["rules"] = self.rules
        return result


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
    counterparty_iban: str = ""

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
            "counterparty_iban": self.counterparty_iban,
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


@dataclass
class SpendingAnalysis:
    """Spending analysis for a single category."""

    category_name: str
    category_path: str
    category_type: CategoryType
    actual: Decimal
    budget: Decimal | None
    budget_period: str
    remaining: Decimal | None
    percent_used: Decimal | None
    transaction_count: int
    compare_actual: Decimal | None = None
    compare_change: Decimal | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "category_name": self.category_name,
            "category_path": self.category_path,
            "category_type": self.category_type.value,
            "actual": str(self.actual),
            "budget": str(self.budget) if self.budget is not None else None,
            "budget_period": self.budget_period,
            "remaining": str(self.remaining) if self.remaining is not None else None,
            "percent_used": str(self.percent_used) if self.percent_used is not None else None,
            "transaction_count": self.transaction_count,
        }
        if self.compare_actual is not None:
            result["compare_actual"] = str(self.compare_actual)
        if self.compare_change is not None:
            result["compare_change"] = str(self.compare_change)
        return result


@dataclass
class CashflowPeriod:
    """Cashflow data for a single period (month or quarter)."""

    period_label: str
    income: Decimal
    expenses: Decimal
    net: Decimal
    transaction_count: int

    def to_dict(self) -> dict:
        return {
            "period_label": self.period_label,
            "income": str(self.income),
            "expenses": str(self.expenses),
            "net": str(self.net),
            "transaction_count": self.transaction_count,
        }


@dataclass
class RecurringTransaction:
    """A detected recurring transaction (subscription/standing order)."""

    merchant_name: str
    category_name: str
    avg_amount: Decimal
    frequency: str  # "monthly", "quarterly", "annual"
    occurrence_count: int
    total_annual_cost: Decimal
    last_date: date
    amount_variance: Decimal

    def to_dict(self) -> dict:
        return {
            "merchant_name": self.merchant_name,
            "category_name": self.category_name,
            "avg_amount": str(self.avg_amount),
            "frequency": self.frequency,
            "occurrence_count": self.occurrence_count,
            "total_annual_cost": str(self.total_annual_cost),
            "last_date": self.last_date.isoformat(),
            "amount_variance": str(self.amount_variance),
        }


@dataclass
class MerchantSummary:
    """Summary of transactions for a single merchant/counterparty."""

    merchant_name: str
    transaction_count: int
    total_amount: Decimal
    avg_amount: Decimal
    categories: list[str] = field(default_factory=list)
    first_date: date | None = None
    last_date: date | None = None
    pct_of_total: Decimal | None = None

    def to_dict(self) -> dict:
        result: dict = {
            "merchant_name": self.merchant_name,
            "transaction_count": self.transaction_count,
            "total_amount": str(self.total_amount),
            "avg_amount": str(self.avg_amount),
            "categories": self.categories,
            "first_date": self.first_date.isoformat() if self.first_date else None,
            "last_date": self.last_date.isoformat() if self.last_date else None,
        }
        if self.pct_of_total is not None:
            result["pct_of_total"] = str(self.pct_of_total)
        return result


@dataclass
class BalanceSnapshot:
    """A balance snapshot for a single account at a point in time."""

    period_label: str
    account_name: str
    balance: Decimal
    change: Decimal

    def to_dict(self) -> dict:
        return {
            "period_label": self.period_label,
            "account_name": self.account_name,
            "balance": str(self.balance),
            "change": str(self.change),
        }


@dataclass
class Security:
    """Represents a single security/holding in a portfolio."""

    name: str
    isin: str
    quantity: float
    purchase_price: float
    current_price: float
    currency: str
    market_value: float
    gain_loss: float
    gain_loss_percent: float
    asset_class: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "isin": self.isin,
            "quantity": self.quantity,
            "purchase_price": self.purchase_price,
            "current_price": self.current_price,
            "currency": self.currency,
            "market_value": self.market_value,
            "gain_loss": self.gain_loss,
            "gain_loss_percent": self.gain_loss_percent,
            "asset_class": self.asset_class,
        }


@dataclass
class Portfolio:
    """Represents a portfolio/depot account with its securities."""

    account_name: str
    account_id: str
    securities: list[Security] = field(default_factory=list)
    total_value: float = 0.0
    total_gain_loss: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "account_name": self.account_name,
            "account_id": self.account_id,
            "securities": [s.to_dict() for s in self.securities],
            "total_value": self.total_value,
            "total_gain_loss": self.total_gain_loss,
        }
