from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.ledger import Posting, post_transaction, reverse_transaction
from backend.models import Base
from backend.stats import compute_stats

CHECKING = "accounts:checking:main"


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _spend(session, category: str, amount: str, on: date):
    return post_transaction(
        session,
        [Posting(CHECKING, -Decimal(amount)), Posting(category, Decimal(amount))],
        date=on,
    )


def _earn(session, amount: str, on: date):
    return post_transaction(
        session,
        [Posting(CHECKING, Decimal(amount)), Posting("income:salary", -Decimal(amount))],
        date=on,
    )


def test_totals_for_a_month(session):
    _earn(session, "2000.00", date(2026, 9, 1))
    _spend(session, "expenses:rent", "900.00", date(2026, 9, 2))
    _spend(session, "expenses:food:groceries", "100.00", date(2026, 9, 10))

    stats = compute_stats(session, "2026-09")

    assert stats["totals"] == {
        "income": "2000.00",
        "spending": "1000.00",
        "net": "1000.00",
        "savings_rate": "0.500",
    }


def test_month_filter_excludes_other_months(session):
    _spend(session, "expenses:rent", "900.00", date(2026, 8, 31))
    _spend(session, "expenses:rent", "950.00", date(2026, 9, 1))

    assert compute_stats(session, "2026-09")["totals"]["spending"] == "950.00"
    assert compute_stats(session, None)["totals"]["spending"] == "1850.00"


def test_subcategories_roll_up_into_their_parent(session):
    _spend(session, "expenses:food:groceries", "60.00", date(2026, 9, 3))
    _spend(session, "expenses:food:takeaway", "40.00", date(2026, 9, 4))
    _spend(session, "expenses:rent", "900.00", date(2026, 9, 1))

    cats = compute_stats(session, "2026-09")["categories"]

    assert [c["name"] for c in cats] == ["rent", "food"]  # biggest first
    food = cats[1]
    assert food["total"] == "100.00"
    assert food["share"] == "0.100"
    assert [(s["name"], s["total"]) for s in food["subcategories"]] == [
        ("groceries", "60.00"),
        ("takeaway", "40.00"),
    ]


def test_reversal_nets_out_in_the_same_month(session):
    txn = _spend(session, "expenses:shopping", "120.00", date(2026, 9, 5))
    reverse_transaction(session, txn.id)

    stats = compute_stats(session, "2026-09")

    assert stats["totals"]["spending"] == "0.00"
    assert stats["categories"] == []  # fully reversed, nothing to show


def test_by_month_history_covers_all_months(session):
    _spend(session, "expenses:rent", "900.00", date(2026, 7, 1))
    _earn(session, "2000.00", date(2026, 8, 1))
    _spend(session, "expenses:coffee", "4.00", date(2026, 8, 2))

    stats = compute_stats(session, "2026-08")

    assert stats["months"] == ["2026-07", "2026-08"]
    assert stats["by_month"][0] == {
        "month": "2026-07",
        "income": "0.00",
        "spending": "900.00",
        "categories": {"rent": "900.00"},
    }
    assert stats["previous"]["month"] == "2026-07"
    assert stats["previous"]["spending"] == "900.00"


def test_savings_rate_is_undefined_without_income(session):
    _spend(session, "expenses:rent", "900.00", date(2026, 9, 1))

    assert compute_stats(session, "2026-09")["totals"]["savings_rate"] is None


def test_undated_transactions_fall_back_to_posting_time(session):
    txn = post_transaction(
        session, [Posting(CHECKING, Decimal("-5.00")), Posting("expenses:misc", Decimal("5.00"))]
    )
    txn.created_at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    session.flush()

    assert compute_stats(session, "2026-06")["totals"]["spending"] == "5.00"


def test_balances_only_list_checking_accounts(session):
    _earn(session, "100.00", date(2026, 9, 1))

    assert compute_stats(session)["balances"] == [{"name": CHECKING, "balance": "100.00"}]
