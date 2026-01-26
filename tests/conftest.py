"""Pytest fixtures for mm-cli tests."""

from datetime import date
from decimal import Decimal

import pytest

from mm_cli.models import (
    Account,
    AccountType,
    Category,
    CategoryType,
    Transaction,
)


@pytest.fixture
def sample_accounts() -> list[Account]:
    """Sample account data for testing."""
    return [
        Account(
            id="DE89370400440532013000",
            name="Girokonto",
            account_number="0532013000",
            bank_name="Commerzbank",
            balance=Decimal("1234.56"),
            currency="EUR",
            account_type=AccountType.CHECKING,
            owner="Max Mustermann",
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            group="Hauptkonten",
            portfolio=False,
        ),
        Account(
            id="DE27100777770209299700",
            name="Tagesgeld",
            account_number="0209299700",
            bank_name="N26",
            balance=Decimal("5000.00"),
            currency="EUR",
            account_type=AccountType.SAVINGS,
            owner="Max Mustermann",
            iban="DE27100777770209299700",
            bic="NTSBDEB1XXX",
            group="Sparkonten",
            portfolio=False,
        ),
    ]


@pytest.fixture
def sample_categories() -> list[Category]:
    """Sample category data for testing."""
    return [
        Category(
            id="550e8400-e29b-41d4-a716-446655440000",
            name="Einkommen",
            category_type=CategoryType.INCOME,
            parent_id=None,
            parent_name=None,
            indentation=0,
            group=True,
            path="Einkommen",
        ),
        Category(
            id="550e8400-e29b-41d4-a716-446655440001",
            name="Gehalt",
            category_type=CategoryType.INCOME,
            parent_id="550e8400-e29b-41d4-a716-446655440000",
            parent_name="Einkommen",
            indentation=1,
            group=False,
            rules='(Gehalt AND name:Cognovis)',
            path="Einkommen\\Gehalt",
        ),
        Category(
            id="550e8400-e29b-41d4-a716-446655440002",
            name="Lebenshaltung",
            category_type=CategoryType.EXPENSE,
            parent_id=None,
            parent_name=None,
            indentation=0,
            group=True,
            path="Lebenshaltung",
        ),
        Category(
            id="550e8400-e29b-41d4-a716-446655440003",
            name="Lebensmittel",
            category_type=CategoryType.EXPENSE,
            parent_id="550e8400-e29b-41d4-a716-446655440002",
            parent_name="Lebenshaltung",
            indentation=1,
            group=False,
            rules='REWE OR Aldi',
            path="Lebenshaltung\\Lebensmittel",
        ),
    ]


@pytest.fixture
def sample_transactions() -> list[Transaction]:
    """Sample transaction data for testing."""
    return [
        Transaction(
            id="12345",
            account_id="DE89370400440532013000",
            account_name="Girokonto",
            booking_date=date(2024, 1, 15),
            value_date=date(2024, 1, 15),
            amount=Decimal("3500.00"),
            currency="EUR",
            name="Arbeitgeber GmbH",
            purpose="Gehalt Januar 2024",
            category_id="550e8400-e29b-41d4-a716-446655440001",
            category_name="Gehalt",
            checkmark=True,
            comment="",
            booked=True,
        ),
        Transaction(
            id="12346",
            account_id="DE89370400440532013000",
            account_name="Girokonto",
            booking_date=date(2024, 1, 16),
            value_date=date(2024, 1, 16),
            amount=Decimal("-45.50"),
            currency="EUR",
            name="REWE",
            purpose="REWE SAGT DANKE",
            category_id="550e8400-e29b-41d4-a716-446655440003",
            category_name="Lebensmittel",
            checkmark=False,
            comment="",
            booked=True,
        ),
        Transaction(
            id="12347",
            account_id="DE89370400440532013000",
            account_name="Girokonto",
            booking_date=date(2024, 1, 17),
            value_date=date(2024, 1, 17),
            amount=Decimal("-12.99"),
            currency="EUR",
            name="Unknown Merchant",
            purpose="Online Purchase",
            category_id=None,
            category_name=None,
            checkmark=False,
            comment="",
            booked=True,
        ),
    ]


@pytest.fixture
def sample_plist_accounts() -> list[dict]:
    """Sample plist data as returned by MoneyMoney for accounts.

    Note: MoneyMoney uses nested arrays for balance: [[amount, currency]]
    and 'group' is a boolean (True for account groups, False for actual accounts).
    """
    return [
        {
            "uuid": "3c782ac3-ed8e-429e-8c21-56bf1324999d",
            "accountNumber": "DE89370400440532013000",
            "name": "Girokonto",
            "bankName": "Commerzbank",
            "bankCode": "COBADEFFXXX",
            "balance": [[1234.56, "EUR"]],  # Nested array format
            "type": "Girokonto",
            "owner": "Max Mustermann",
            "group": False,  # False = actual account, True = account group
            "portfolio": False,
        },
    ]


@pytest.fixture
def sample_plist_categories() -> list[dict]:
    """Sample plist data as returned by MoneyMoney for categories.

    MoneyMoney returns a flat list with 'indentation' levels and 'group'
    flags instead of nested 'children' arrays.
    """
    return [
        {
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "name": "Einkommen",
            "type": 1,
            "indentation": 0,
            "group": True,
            "rules": "",
            "budget": {"amount": 0.0, "available": 0.0, "period": "monthly"},
        },
        {
            "uuid": "550e8400-e29b-41d4-a716-446655440001",
            "name": "Gehalt",
            "type": 1,
            "indentation": 1,
            "group": False,
            "rules": "(Gehalt AND name:Cognovis)",
            "budget": {},
        },
        {
            "uuid": "550e8400-e29b-41d4-a716-446655440002",
            "name": "Lebenshaltung",
            "type": 0,
            "indentation": 0,
            "group": True,
            "rules": "",
            "budget": {},
        },
        {
            "uuid": "550e8400-e29b-41d4-a716-446655440003",
            "name": "Lebensmittel",
            "type": 0,
            "indentation": 1,
            "group": False,
            "rules": "REWE OR Aldi",
            "budget": {},
        },
    ]


@pytest.fixture
def sample_plist_transactions() -> list[dict]:
    """Sample plist data as returned by MoneyMoney for transactions."""
    return [
        {
            "id": "12345",
            "accountNumber": "DE89370400440532013000",
            "accountName": "Girokonto",
            "bookingDate": date(2024, 1, 15),
            "valueDate": date(2024, 1, 15),
            "amount": 3500.00,
            "currency": "EUR",
            "name": "Arbeitgeber GmbH",
            "purpose": "Gehalt Januar 2024",
            "categoryUuid": "550e8400-e29b-41d4-a716-446655440001",
            "category": "Gehalt",
            "checkmark": True,
            "comment": "",
            "booked": True,
        },
    ]
