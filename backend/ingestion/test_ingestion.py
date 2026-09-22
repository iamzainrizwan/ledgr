from decimal import Decimal
from pathlib import Path

import pytest
from common import ParsedStatement
from hsbc import parse_hsbc_pdf


def main():
    p = Path("../../priv/2026-06-28_Bank A_C_Statement.pdf")
    print("67")
    ps = parse_hsbc_pdf(p)
    print(ps.opening_balance)
    print(ps.closing_balance)


def test_hsbc():
    p = Path("../../priv/2026-06-28_Bank A_C_Statement.pdf")
    hsbc_parsed: ParsedStatement = parse_hsbc_pdf(p)
    assert hsbc_parsed.opening_balance == Decimal("754.01")
    assert hsbc_parsed.opening_balance == Decimal("67.73")


if __name__ == "__main__":
    main()
