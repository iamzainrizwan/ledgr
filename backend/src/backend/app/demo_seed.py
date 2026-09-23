from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.ingestion.common import ParsedStatement, ParsedTransaction
from backend.ingestion.orchestrator import categorize_pending, stage_statement
from backend.models import Account, Entry, PendingTransaction, Transaction

DEMO_ACCOUNT = "demo"
OPENING_BALANCE = Decimal("1200.00")

# SYNTHETIC DATA: invented but plausible transactions so the demo has a few
# months of history for the stats step. None of this is a real statement.
CATEGORIES = {
    "SALARY - ACME CORP": "income:salary",
    "RENT PAYMENT - LANDLORD LTD": "expenses:rent",
    "TESCO STORES 4521": "expenses:groceries",
    "NETFLIX.COM": "expenses:subscriptions",
    "SPOTIFY UK": "expenses:subscriptions",
    "TFL TRAVEL CHARGE": "expenses:transport",
    "COSTA COFFEE": "expenses:coffee",
    "AMAZON MARKETPLACE": "expenses:shopping",
    "OCTOPUS ENERGY": "expenses:utilities",
    "DISHOOM KINGS CROSS": "expenses:dining",
    "BOOTS PHARMACY": "expenses:health",
    "ODEON CINEMAS": "expenses:entertainment",
    "TRANSFER TO SAVINGS": "transfer:savings",
    "AMAZON REFUND": "income:refund",
}


def _t(day: str, description: str, amount: str) -> ParsedTransaction:
    return ParsedTransaction(day, description, Decimal(amount))


# one categorised statement per month; each opens where the last closed
MONTHS = [
    [
        _t("2026-06-01", "SALARY - ACME CORP", "2100.00"),
        _t("2026-06-02", "RENT PAYMENT - LANDLORD LTD", "-950.00"),
        _t("2026-06-03", "OCTOPUS ENERGY", "-68.40"),
        _t("2026-06-04", "TESCO STORES 4521", "-52.75"),
        _t("2026-06-05", "NETFLIX.COM", "-12.99"),
        _t("2026-06-08", "TFL TRAVEL CHARGE", "-41.30"),
        _t("2026-06-11", "TESCO STORES 4521", "-61.10"),
        _t("2026-06-14", "DISHOOM KINGS CROSS", "-48.50"),
        _t("2026-06-18", "TESCO STORES 4521", "-47.85"),
        _t("2026-06-20", "TRANSFER TO SAVINGS", "-300.00"),
        _t("2026-06-24", "COSTA COFFEE", "-4.15"),
        _t("2026-06-27", "AMAZON MARKETPLACE", "-34.99"),
    ],
    [
        _t("2026-07-01", "SALARY - ACME CORP", "2100.00"),
        _t("2026-07-02", "RENT PAYMENT - LANDLORD LTD", "-950.00"),
        _t("2026-07-03", "OCTOPUS ENERGY", "-61.20"),
        _t("2026-07-04", "TESCO STORES 4521", "-58.40"),
        _t("2026-07-05", "NETFLIX.COM", "-12.99"),
        _t("2026-07-06", "SPOTIFY UK", "-11.99"),
        _t("2026-07-09", "TFL TRAVEL CHARGE", "-37.90"),
        _t("2026-07-12", "ODEON CINEMAS", "-23.00"),
        _t("2026-07-15", "TESCO STORES 4521", "-66.25"),
        _t("2026-07-18", "AMAZON MARKETPLACE", "-189.00"),
        _t("2026-07-20", "TRANSFER TO SAVINGS", "-300.00"),
        _t("2026-07-23", "AMAZON REFUND", "45.00"),
        _t("2026-07-26", "DISHOOM KINGS CROSS", "-62.30"),
        _t("2026-07-29", "TESCO STORES 4521", "-49.60"),
    ],
    [
        _t("2026-08-01", "SALARY - ACME CORP", "2100.00"),
        _t("2026-08-02", "RENT PAYMENT - LANDLORD LTD", "-950.00"),
        _t("2026-08-03", "OCTOPUS ENERGY", "-55.80"),
        _t("2026-08-05", "NETFLIX.COM", "-12.99"),
        _t("2026-08-06", "SPOTIFY UK", "-11.99"),
        _t("2026-08-07", "TESCO STORES 4521", "-71.35"),
        _t("2026-08-10", "TFL TRAVEL CHARGE", "-44.10"),
        _t("2026-08-13", "BOOTS PHARMACY", "-18.60"),
        _t("2026-08-16", "TESCO STORES 4521", "-54.90"),
        _t("2026-08-19", "COSTA COFFEE", "-3.80"),
        _t("2026-08-20", "TRANSFER TO SAVINGS", "-300.00"),
        _t("2026-08-22", "DISHOOM KINGS CROSS", "-39.75"),
        _t("2026-08-28", "TESCO STORES 4521", "-63.20"),
    ],
    [
        _t("2026-09-01", "SALARY - ACME CORP", "2100.00"),
        _t("2026-09-02", "RENT PAYMENT - LANDLORD LTD", "-950.00"),
        _t("2026-09-03", "TESCO STORES 4521", "-64.30"),
        _t("2026-09-05", "NETFLIX.COM", "-12.99"),
        _t("2026-09-06", "TFL TRAVEL CHARGE", "-38.20"),
        _t("2026-09-09", "COSTA COFFEE", "-4.15"),
        _t("2026-09-12", "TESCO STORES 4521", "-57.90"),
        _t("2026-09-18", "AMAZON MARKETPLACE", "-129.91"),
    ],
]

# left pending, so the categorise step has something to do. CORNER BAKERY is
# new, so it's the one row with no suggestion from history.
PENDING = [
    _t("2026-09-20", "TESCO STORES 4521", "-41.20"),
    _t("2026-09-21", "COSTA COFFEE", "-3.80"),
    _t("2026-09-22", "TFL TRAVEL CHARGE", "-35.60"),
    _t("2026-09-23", "SQ *CORNER BAKERY", "-85.84"),
]


def _wipe(session: Session) -> None:
    session.execute(delete(Entry))
    session.execute(delete(Transaction))
    session.execute(delete(PendingTransaction))
    session.execute(delete(Account))
    session.commit()


def _statement(opening: Decimal, txns: list[ParsedTransaction]) -> ParsedStatement:
    return ParsedStatement(
        opening_balance=opening,
        closing_balance=opening + sum((t.amount for t in txns), Decimal("0")),
        transactions=txns,
    )


def reset_and_seed(session: Session) -> None:
    """
    Wipes everything and reloads the synthetic demo ledger above - a demo-only
    reset utility (there's no auth on this API, so a public demo needs a
    one-click way back to a clean, presentable state). Not something a real
    deployment of this app would ever expose.
    """
    _wipe(session)

    balance = OPENING_BALANCE
    for txns in MONTHS:
        statement = _statement(balance, txns)
        result = stage_statement(session, DEMO_ACCOUNT, statement)
        # categorise every month fully so the next statement's continuity
        # check lines up (no reconciliation adjustment muddying the demo)
        for pending in result.newly_staged:
            categorize_pending(session, pending.id, CATEGORIES[pending.description])
        balance = statement.closing_balance

    stage_statement(session, DEMO_ACCOUNT, _statement(balance, PENDING))
