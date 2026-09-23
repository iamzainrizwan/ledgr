from decimal import Decimal
from pathlib import Path

import pandas as pd
from backend.ingestion.common import ParsedStatement, ParsedTransaction, StatementParseError


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
    return ParsedStatement(
        transactions=txns,
        opening_balance=Decimal(df.iloc[0]["Balance"]),
        closing_balance=Decimal(df.iloc[-1]["Balance"]),
    )
