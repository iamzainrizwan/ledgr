from decimal import Decimal
from pathlib import Path

from backend.ingestion.common import ParsedStatement
from backend.ingestion.hsbc import parse_hsbc_pdf

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRIV_DIR = REPO_ROOT / "priv"


def test_hsbc():
    p = PRIV_DIR / "2026-06-28_Bank A_C_Statement.pdf"
    hsbc_parsed: ParsedStatement = parse_hsbc_pdf(p)
    assert hsbc_parsed.opening_balance == Decimal("754.01")
    assert hsbc_parsed.closing_balance == Decimal("67.73")
