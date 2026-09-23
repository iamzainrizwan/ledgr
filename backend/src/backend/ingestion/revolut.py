from decimal import Decimal
from pathlib import Path

import pandas as pd
from backend.ingestion.common import (
    ParsedStatement,
    ParsedTransaction,
    StatementParseError,
    self_validate,
)


def parse_revolut_excel(path: Path) -> ParsedStatement:
    txns: list[ParsedTransaction] = []
    df = None
    try:
        df = pd.read_excel(path)
    except Exception:
        df = pd.read_csv(path)
    for _, r in df.iterrows():
        txns.append(
            ParsedTransaction(
                date=str(r["Started Date"]).split(" ")[0],
                description=str(r["Description"]),
                amount=Decimal(str(r["Amount"])),
            )
        )
    if df.empty:
        raise StatementParseError("Statement contains no transactions.")
    # "Balance" is the balance AFTER that row's transaction posts, so the
    # statement's opening balance is the first row's balance minus its own
    # transaction, not the first row's balance itself.
    first_row_balance = Decimal(str(df.iloc[0]["Balance"]))
    opening_balance = first_row_balance - txns[0].amount
    closing_balance = Decimal(str(df.iloc[-1]["Balance"]))
    self_validate(txns, opening_balance=opening_balance, closing_balance=closing_balance)
    return ParsedStatement(
        transactions=txns,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
    )
