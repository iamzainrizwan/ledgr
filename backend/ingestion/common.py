from decimal import Decimal
from typing import NamedTuple


class ParsedTransaction(NamedTuple):
    """A row extracted from a statement, before it becomes a Posting"""

    date: str  # ISO DATE, "YYYY-MM-DD"
    description: str
    amount: Decimal


class StatementSelfCheckError(ValueError):
    """Parsed transactions don't match the statement's own opening/closing balance."""


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
) -> None:
    if prior_closing_balance != next_opening_balance:
        raise StatementSelfCheckError
