from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.ledger import (
    Posting,
    get_balance,
    get_or_create_account,
    post_transaction,
    reverse_transaction,
)
from backend.models import Base, Transaction


@pytest.fixture
def session():
    """
    Fresh in memory sqlite db per test.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_accounts(session):
    account1 = get_or_create_account(session, "Assets:Checking:HSBC")
    account2 = get_or_create_account(session, "Assets:Checking:HSBC")
    assert account1.id == account2.id


def test_balance_as_query(session):
    account_checking = get_or_create_account(session, "Assets:Checking")

    assert get_balance(session, account_checking.name) == Decimal("0")

    post_transaction(
        session,
        [
            Posting("Assets:Checking:HSBC", Decimal("20000")),
            Posting("Equity:OpeningBalance", Decimal("-20000")),
        ],
    )

    post_transaction(
        session,
        [
            Posting("Assets:Checking:Revolut", Decimal("100")),
            Posting("Equity:OpeningBalance", Decimal("-100")),
        ],
    )

    post_transaction(
        session,
        [
            Posting("Assets:Checking:HSBC", Decimal("-2000")),
            Posting("Expenses:Rent", Decimal("2000")),
        ],
    )

    post_transaction(
        session,
        [
            Posting("Assets:Checking:Revolut", Decimal("-10")),
            Posting("Expenses:Travel", Decimal("10")),
        ],
    )

    assert get_balance(session, "Assets:Checking:Revolut") == Decimal("90")
    assert get_balance(session, "Assets:Checking:HSBC") == Decimal("18000")
    assert get_balance(session, "Assets:Checking") == Decimal("0")
    assert get_balance(session, "Assets:Checking", include_children=True) == Decimal(
        "18090"
    )


def test_idempotency(session):
    tn1 = post_transaction(
        session,
        [
            Posting("Assets:Checking:Revolut", Decimal("2000")),
            Posting("Equity:OpeningBalance", Decimal("-2000")),
        ],
        external_id="test_id",
    )

    balance1 = get_balance(session, "Assets:Checking:Revolut")

    tn2 = post_transaction(
        session,
        [
            Posting("Assets:Checking:Revolut", Decimal("3000")),
            Posting("Equity:OpeningBalance", Decimal("-3000")),
        ],
        external_id="test_id",
    )

    assert tn1.id == tn2.id
    assert balance1 == get_balance(session, "Assets:Checking:Revolut")
    count = session.scalar(select(func.count()).select_from(Transaction))
    assert count == 1


def test_reversal_keeps_original_date(session):
    original = post_transaction(
        session,
        [Posting("assets:cash", Decimal("-5.00")), Posting("expenses:coffee", Decimal("5.00"))],
        date=date(2026, 4, 30),
    )

    reversal = reverse_transaction(session, original.id)

    # same day as what it corrects, so the month's totals net to zero
    assert reversal.date == date(2026, 4, 30)
