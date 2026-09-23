from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.ingestion.common import ParsedStatement, ParsedTransaction
from backend.ingestion.orchestrator import categorize_pending, stage_statement
from backend.models import Account, Entry, PendingTransaction, Transaction

DEMO_ACCOUNT = "demo"


def _wipe(session: Session) -> None:
    session.execute(delete(Entry))
    session.execute(delete(Transaction))
    session.execute(delete(PendingTransaction))
    session.execute(delete(Account))
    session.commit()


def reset_and_seed(session: Session) -> None:
    """
    Wipes everything and reloads a small synthetic demo ledger — this is a
    demo-only reset utility (there's no auth on this API, so a public demo
    needs a one-click way back to a clean, presentable state). Not something
    a real deployment of this app would ever expose.
    """
    _wipe(session)

    statement_1 = ParsedStatement(
        opening_balance=Decimal("1200.00"),
        closing_balance=Decimal("2042.55"),
        transactions=[
            ParsedTransaction("01 Sep 26", "SALARY - ACME CORP", Decimal("2100.00")),
            ParsedTransaction("02 Sep 26", "RENT PAYMENT - LANDLORD LTD", Decimal("-950.00")),
            ParsedTransaction("03 Sep 26", "TESCO STORES 4521", Decimal("-64.30")),
            ParsedTransaction("05 Sep 26", "NETFLIX.COM", Decimal("-12.99")),
            ParsedTransaction("06 Sep 26", "TFL TRAVEL CHARGE", Decimal("-38.20")),
            ParsedTransaction("09 Sep 26", "COSTA COFFEE", Decimal("-4.15")),
            ParsedTransaction("12 Sep 26", "TESCO STORES 4521", Decimal("-57.90")),
            ParsedTransaction("18 Sep 26", "AMAZON MARKETPLACE", Decimal("-129.91")),
        ],
    )
    result_1 = stage_statement(session, DEMO_ACCOUNT, statement_1)
    categories = {
        "SALARY - ACME CORP": "income:salary",
        "RENT PAYMENT - LANDLORD LTD": "expenses:rent",
        "TESCO STORES 4521": "expenses:groceries",
        "NETFLIX.COM": "expenses:entertainment",
        "TFL TRAVEL CHARGE": "expenses:transport",
        "COSTA COFFEE": "expenses:coffee",
        "AMAZON MARKETPLACE": "expenses:shopping",
    }
    # fully categorize statement 1 so statement 2's continuity check lines up
    # cleanly (no surprise reconciliation adjustment muddying the demo) —
    # statement 2's transactions are the ones left pending for the review tab.
    for pending in result_1.newly_staged:
        categorize_pending(session, pending.id, categories[pending.description])

    statement_2 = ParsedStatement(
        opening_balance=Decimal("2042.55"),
        closing_balance=Decimal("1876.11"),
        transactions=[
            ParsedTransaction("20 Sep 26", "TESCO STORES 4521", Decimal("-41.20")),
            ParsedTransaction("21 Sep 26", "COSTA COFFEE", Decimal("-3.80")),
            ParsedTransaction("22 Sep 26", "TFL TRAVEL CHARGE", Decimal("-35.60")),
            ParsedTransaction("23 Sep 26", "SQ *CORNER BAKERY", Decimal("-85.84")),
        ],
    )
    stage_statement(session, DEMO_ACCOUNT, statement_2)
