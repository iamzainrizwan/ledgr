from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.ingestion.common import ParsedStatement, ParsedTransaction
from backend.ingestion.orchestrator import (
    _account_name,
    categorize_pending,
    categorize_pending_bulk,
    stage_statement,
    suggest_category,
)
from backend.ledger import get_balance
from backend.models import Base


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _stmt(opening: str, closing: str, txns: list[ParsedTransaction]) -> ParsedStatement:
    return ParsedStatement(
        opening_balance=Decimal(opening), closing_balance=Decimal(closing), transactions=txns
    )


def test_first_statement_seeds_and_stages(session):
    stmt = _stmt("100.00", "80.00", [ParsedTransaction("01 Jan 26", "Shop", Decimal("-20.00"))])

    result = stage_statement(session, "acc1", stmt)

    assert result.is_first_statement is True
    assert result.balance_adjustment == 0
    assert len(result.newly_staged) == 1
    # the opening balance seed is posted immediately; the transaction itself
    # is still pending, so the ledger only reflects the seed so far.
    assert get_balance(session, _account_name("acc1")) == Decimal("100.00")


def test_categorize_posts_and_clears_pending(session):
    stmt = _stmt("100.00", "80.00", [ParsedTransaction("01 Jan 26", "Shop", Decimal("-20.00"))])
    result = stage_statement(session, "acc2", stmt)

    categorize_pending(session, result.newly_staged[0].id, "expenses:shop")

    assert get_balance(session, _account_name("acc2")) == Decimal("80.00")
    assert get_balance(session, "expenses:shop") == Decimal("20.00")


def test_reingest_same_statement_is_noop(session):
    stmt = _stmt("100.00", "80.00", [ParsedTransaction("01 Jan 26", "Shop", Decimal("-20.00"))])
    stage_statement(session, "acc3", stmt)

    result2 = stage_statement(session, "acc3", stmt)

    assert result2.newly_staged == []
    assert result2.balance_adjustment == 0


def test_gap_between_statements_gets_reconciled(session):
    stmt1 = _stmt("100.00", "80.00", [ParsedTransaction("01 Jan 26", "Shop", Decimal("-20.00"))])
    r1 = stage_statement(session, "acc4", stmt1)
    categorize_pending(session, r1.newly_staged[0].id, "expenses:shop")

    # deliberately skip ahead: next statement opens at 50, not the 80 the
    # ledger actually shows, so it should get plugged with a -30 adjustment.
    stmt2 = _stmt("50.00", "40.00", [ParsedTransaction("05 Jan 26", "Cafe", Decimal("-10.00"))])
    r2 = stage_statement(session, "acc4", stmt2)

    assert r2.balance_adjustment == Decimal("-30.00")
    categorize_pending(session, r2.newly_staged[0].id, "expenses:cafe")
    assert get_balance(session, _account_name("acc4")) == Decimal("40.00")


def test_suggest_category_from_history(session):
    stmt = _stmt("100.00", "80.00", [ParsedTransaction("01 Jan 26", "Tesco", Decimal("-20.00"))])
    result = stage_statement(session, "acc5", stmt)
    categorize_pending(session, result.newly_staged[0].id, "expenses:groceries")

    suggestion = suggest_category(session, _account_name("acc5"), "Tesco")

    assert suggestion == "expenses:groceries"


def test_categorize_bulk(session):
    stmt = _stmt(
        "100.00",
        "70.00",
        [
            ParsedTransaction("01 Jan 26", "A", Decimal("-10.00")),
            ParsedTransaction("02 Jan 26", "B", Decimal("-20.00")),
        ],
    )
    result = stage_statement(session, "acc6", stmt)
    categorizations = {p.id: "expenses:misc" for p in result.newly_staged}

    txns = categorize_pending_bulk(session, categorizations)

    assert len(txns) == 2
    assert get_balance(session, _account_name("acc6")) == Decimal("70.00")
