from decimal import Decimal
from pathlib import Path

from backend.ingestion.revolut import parse_revolut_excel

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRIV_DIR = REPO_ROOT / "priv"


def test_revolut_reconciles():
    p = PRIV_DIR / "account-statement_2026-08-01_2026-08-31_en-gb_f088bc.xlsx"
    result = parse_revolut_excel(p)

    assert result.opening_balance == Decimal("85.07")
    assert result.closing_balance == Decimal("10.87")
    assert result.opening_balance + sum(
        t.amount for t in result.transactions
    ) == result.closing_balance
