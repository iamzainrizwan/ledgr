from decimal import Decimal
from pathlib import Path

import pandas as pd
from common import (
    ParsedTransaction,
    check_cross_statement_continuity,
    self_validate,
)


def parse_revolut_excel(path: Path) -> list[ParsedTransaction]:
    txns: list[ParsedTransaction] = []
    df = pd.read_excel(path, sheet_name="in")
    for _, r in df.iterrows():
        txns.append(
            ParsedTransaction(
                date=str(r["Started Date"]).split(" ")[0],
                description=str(r["Description"]),
                amount=Decimal(str(r["Amount"])),
            )
        )

    return txns
