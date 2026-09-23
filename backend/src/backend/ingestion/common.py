from datetime import date, datetime
from decimal import Decimal
from typing import NamedTuple


class ParsedTransaction(NamedTuple):
    """A row extracted from a statement, before it becomes a Posting"""

    date: str  # ISO DATE, "YYYY-MM-DD"
    description: str
    amount: Decimal


def parse_statement_date(value: str) -> date:
    """
    Parses a statement date into a real date. ISO ("2026-09-01") is the
    documented format; "01 Sep 26" / "01 Sep 2026" is also accepted because
    HSBC's parser emitted that before it was normalised, and pending rows
    staged back then still carry it.
    """
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d %b %y", "%d %b %Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised statement date: {value!r}")


class ParsedStatement(NamedTuple):
    """A summary of a statement after it has been parsed by a parser"""

    opening_balance: Decimal
    closing_balance: Decimal
    transactions: list[ParsedTransaction]


class StatementSelfCheckError(ValueError):
    """Parsed transactions don't match the statement's own opening/closing balance."""


class StatementParseError(ValueError):
    """Error that occurs when a parsed document does not have the expected shape."""


def self_validate(
    parsed: list[ParsedTransaction],
    *,
    opening_balance: Decimal,
    closing_balance: Decimal,
) -> None:
    for t in parsed:
        opening_balance += t.amount
    if opening_balance != closing_balance:
        raise StatementSelfCheckError


def check_cross_statement_continuity(
    prior_closing_balance: Decimal, next_opening_balance: Decimal
) -> Decimal:
    """
    Returns the gap between the two balances (zero if they already agree).
    Deciding what to do about a nonzero gap (e.g. a skipped statement) is an
    ingestion/orchestration concern, not a parsing concern, so this only reports
    the discrepancy rather than raising.
    """
    return next_opening_balance - prior_closing_balance
