"""Pytest fixtures for mm-cli tests."""

from datetime import date
from decimal import Decimal

import pytest

from mm_cli.models import (
    Account,
    AccountType,
    Category,
    CategoryType,
    Portfolio,
    Security,
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
def rich_transactions() -> list[Transaction]:
    """Richer transaction set for recurring/merchant/cashflow analysis."""
    txs: list[Transaction] = []
    # Monthly salary over 6 months
    for m in range(1, 7):
        txs.append(Transaction(
            id=f"sal-{m}",
            account_id="DE89370400440532013000",
            account_name="Girokonto",
            booking_date=date(2025, m, 28),
            value_date=date(2025, m, 28),
            amount=Decimal("3500.00"),
            currency="EUR",
            name="Arbeitgeber GmbH",
            purpose=f"Gehalt {m}/2025",
            category_id="550e8400-e29b-41d4-a716-446655440001",
            category_name="Gehalt",
        ))
    # Monthly Netflix subscription over 6 months
    for m in range(1, 7):
        txs.append(Transaction(
            id=f"nf-{m}",
            account_id="DE89370400440532013000",
            account_name="Girokonto",
            booking_date=date(2025, m, 5),
            value_date=date(2025, m, 5),
            amount=Decimal("-12.99"),
            currency="EUR",
            name="NETFLIX.COM",
            purpose="Netflix Monthly",
            category_id="cat-streaming",
            category_name="Streaming",
        ))
    # Several REWE transactions
    for m in range(1, 7):
        for day in (3, 15):
            txs.append(Transaction(
                id=f"rewe-{m}-{day}",
                account_id="DE89370400440532013000",
                account_name="Girokonto",
                booking_date=date(2025, m, day),
                value_date=date(2025, m, day),
                amount=Decimal("-45.50"),
                currency="EUR",
                name="REWE",
                purpose="REWE SAGT DANKE",
                category_id="550e8400-e29b-41d4-a716-446655440003",
                category_name="Lebensmittel",
            ))
    # Client payment (income)
    for m in (1, 3, 5):
        txs.append(Transaction(
            id=f"client-{m}",
            account_id="DE89370400440532013000",
            account_name="Girokonto",
            booking_date=date(2025, m, 10),
            value_date=date(2025, m, 10),
            amount=Decimal("2500.00"),
            currency="EUR",
            name="Cognovis GmbH",
            purpose="Rechnung 2025-{m}",
            category_id="cat-invoice",
            category_name="Rechnungen",
        ))
    # Internal transfer (credit card settlement) - should be excluded
    for m in range(1, 7):
        txs.append(Transaction(
            id=f"kk-{m}",
            account_id="DE89370400440532013000",
            account_name="Girokonto",
            booking_date=date(2025, m, 20),
            value_date=date(2025, m, 20),
            amount=Decimal("-500.00"),
            currency="EUR",
            name="American Express Europe S.A.",
            purpose="Kreditkarten Abrechnung",
            category_id="cat-kk-abrechnung",
            category_name="Kreditkarten Abrechnung",
        ))
    return txs


@pytest.fixture
def transfer_categories() -> list[Category]:
    """Categories including the Umbuchungen (transfer) hierarchy."""
    return [
        Category(
            id="cat-umbuchungen", name="Umbuchungen",
            category_type=CategoryType.EXPENSE,
            indentation=0, group=True,
            path="Umbuchungen",
        ),
        Category(
            id="cat-echte-umbuchung", name="Echte Umbuchung",
            category_type=CategoryType.EXPENSE,
            indentation=1, group=False,
            path="Umbuchungen\\Echte Umbuchung",
        ),
        Category(
            id="cat-kk-abrechnung", name="Kreditkarten Abrechnung",
            category_type=CategoryType.EXPENSE,
            indentation=1, group=False,
            path="Umbuchungen\\Kreditkarten Abrechnung",
        ),
        Category(
            id="550e8400-e29b-41d4-a716-446655440001",
            name="Gehalt",
            category_type=CategoryType.INCOME,
            path="Einkommen\\Gehalt",
        ),
        Category(
            id="cat-streaming", name="Streaming",
            category_type=CategoryType.EXPENSE,
            path="Haushalt\\Streaming",
        ),
        Category(
            id="550e8400-e29b-41d4-a716-446655440003",
            name="Lebensmittel",
            category_type=CategoryType.EXPENSE,
            path="Haushalt\\Lebensmittel",
        ),
        Category(
            id="cat-invoice", name="Rechnungen",
            category_type=CategoryType.INCOME,
            path="Einkommen\\Rechnungen",
        ),
    ]


@pytest.fixture
def sample_plist_accounts() -> list[dict]:
    """Sample plist data as returned by MoneyMoney for accounts.

    Note: MoneyMoney uses nested arrays for balance: [[amount, currency]]
    and 'group' is a boolean (True for account groups, False for actual accounts).
    Group items act as section headers; subsequent non-group items belong to
    the most recent group.
    """
    return [
        {
            "name": "Hauptkonten",
            "group": True,
        },
        {
            "uuid": "3c782ac3-ed8e-429e-8c21-56bf1324999d",
            "accountNumber": "DE89370400440532013000",
            "name": "Girokonto",
            "bankName": "Commerzbank",
            "bankCode": "COBADEFFXXX",
            "balance": [[1234.56, "EUR"]],
            "type": "Girokonto",
            "owner": "Max Mustermann",
            "group": False,
            "portfolio": False,
        },
        {
            "name": "Sparkonten",
            "group": True,
        },
        {
            "uuid": "4d893bc4-fe9f-530f-9d32-67cf2435000e",
            "accountNumber": "DE27100777770209299700",
            "name": "Tagesgeld",
            "bankName": "N26",
            "bankCode": "NTSBDEB1XXX",
            "balance": [[5000.00, "EUR"]],
            "type": "Tagesgeldkonto",
            "owner": "Max Mustermann",
            "group": False,
            "portfolio": False,
        },
        {
            "name": "Aufgelöst",
            "group": True,
        },
        {
            "uuid": "5e904cd5-0fa0-641g-ae43-78dg3546111f",
            "accountNumber": "DE00000000000000000000",
            "name": "Altes Konto",
            "bankName": "Sparkasse",
            "bankCode": "SPKADE00",
            "balance": [[0.00, "EUR"]],
            "type": "Girokonto",
            "owner": "Max Mustermann",
            "group": False,
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
            "budget": {"amount": 500.0, "available": 50.0, "period": "monthly"},
        },
    ]


@pytest.fixture
def sample_plist_transactions() -> list[dict]:
    """Sample plist data as returned by MoneyMoney for transactions."""
    return [
        {
            "id": "12345",
            "accountUuid": "3c782ac3-ed8e-429e-8c21-56bf1324999d",
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


@pytest.fixture
def multi_group_accounts() -> list[Account]:
    """Accounts across two groups for IBAN transfer detection tests."""
    return [
        Account(
            id="uuid-privat-giro",
            name="Privat Girokonto",
            account_number="0532013000",
            bank_name="Commerzbank",
            balance=Decimal("1000.00"),
            currency="EUR",
            account_type=AccountType.CHECKING,
            iban="DE89370400440532013000",
            group="Privat",
        ),
        Account(
            id="uuid-privat-tagesgeld",
            name="Privat Tagesgeld",
            account_number="0209299700",
            bank_name="N26",
            balance=Decimal("5000.00"),
            currency="EUR",
            account_type=AccountType.SAVINGS,
            iban="DE27100777770209299700",
            group="Privat",
        ),
        Account(
            id="uuid-cognovis-giro",
            name="cognovis Geschaeftskonto",
            account_number="0999888777",
            bank_name="Commerzbank",
            balance=Decimal("20000.00"),
            currency="EUR",
            account_type=AccountType.CHECKING,
            iban="DE55370400440999888777",
            group="cognovis",
        ),
    ]


@pytest.fixture
def sample_portfolios() -> list[Portfolio]:
    """Sample portfolio data for testing."""
    return [
        Portfolio(
            account_name="Depot Commerzbank",
            account_id="depot-uuid-1",
            securities=[
                Security(
                    name="iShares Core MSCI World",
                    isin="IE00B4L5Y983",
                    quantity=50.0,
                    purchase_price=65.00,
                    current_price=78.50,
                    currency="EUR",
                    market_value=3925.00,
                    gain_loss=675.00,
                    gain_loss_percent=20.77,
                    asset_class="Equity",
                ),
                Security(
                    name="Xtrackers DAX ETF",
                    isin="LU0274211480",
                    quantity=20.0,
                    purchase_price=140.00,
                    current_price=132.50,
                    currency="EUR",
                    market_value=2650.00,
                    gain_loss=-150.00,
                    gain_loss_percent=-5.36,
                    asset_class="Equity",
                ),
            ],
            total_value=6575.00,
            total_gain_loss=525.00,
        ),
    ]


@pytest.fixture
def sample_plist_portfolio() -> list[dict]:
    """Sample plist data as returned by MoneyMoney for portfolio export."""
    return [
        {
            "name": "Depot Commerzbank",
            "uuid": "depot-uuid-1",
            "securities": [
                {
                    "name": "iShares Core MSCI World",
                    "isin": "IE00B4L5Y983",
                    "quantity": 50.0,
                    "purchasePrice": 65.00,
                    "price": 78.50,
                    "currency": "EUR",
                    "marketValue": 3925.00,
                    "assetClass": "Equity",
                },
                {
                    "name": "Xtrackers DAX ETF",
                    "isin": "LU0274211480",
                    "quantity": 20.0,
                    "purchasePrice": 140.00,
                    "price": 132.50,
                    "currency": "EUR",
                    "marketValue": 2650.00,
                    "assetClass": "Equity",
                },
            ],
        },
    ]
