from decimal import Decimal
from pathlib import Path

import pandas as pd
from common import (
    ParsedTransaction,
)


def parse_revolut_excel(path: Path) -> list[ParsedTransaction]:
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

    return txns
