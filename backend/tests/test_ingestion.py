from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.ingestion.common import ParsedStatement, parse_statement_date
from backend.ingestion.hsbc import parse_hsbc_pdf

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRIV_DIR = REPO_ROOT / "priv"


def test_hsbc():
    p = PRIV_DIR / "2026-06-28_Bank A_C_Statement.pdf"
    hsbc_parsed: ParsedStatement = parse_hsbc_pdf(p)
    assert hsbc_parsed.opening_balance == Decimal("754.01")
    assert hsbc_parsed.closing_balance == Decimal("67.73")


def test_hsbc_dates_are_iso():
    # common.py documents ISO dates; HSBC used to emit "01 Sep 26"
    parsed = parse_hsbc_pdf(PRIV_DIR / "2026-06-28_Bank A_C_Statement.pdf")
    for txn in parsed.transactions:
        assert date.fromisoformat(txn.date)


def test_parse_statement_date_accepts_iso_and_legacy():
    assert parse_statement_date("2026-09-01") == date(2026, 9, 1)
    assert parse_statement_date("01 Sep 26") == date(2026, 9, 1)
    assert parse_statement_date("01 Sep 2026") == date(2026, 9, 1)
