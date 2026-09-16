from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pdfplumber
from common import ParsedTransaction

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

AMOUNT_X0_MIN, AMOUNT_X0_MAX = 350, 500
AMOUNT_SIGN_BOUNDARY = 400  # x0 < this = money out, >= this = money in
BALANCE_X0_MIN, BALANCE_X0_MAX = 520, 550


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except Exception:
        return None


@dataclass
class ClassifiedRow:
    date: str | None
    amount: Decimal | None
    balance: Decimal | None
    description_words: list[str]


def _extract_date(row) -> str | None:
    if len(row) < 3:
        return None
    day, month, year = row[0], row[1], row[2]
    if day["text"].isdigit() and month["text"] in MONTHS and year["text"].isdigit():
        return f"{int(day['text']):02d} {month['text']} {int(year['text'])}"
    return None


def _classify_row(row) -> ClassifiedRow:
    date = _extract_date(row)
    consumed = 3 if date else 0

    amount = None
    balance = None
    description_words = []

    for i, word in enumerate(row):
        if i < consumed:
            continue

        value = _decimal(word["text"])
        x0 = word["x0"]

        if value is not None and AMOUNT_X0_MIN <= x0 < AMOUNT_X0_MAX:
            amount = value if x0 >= AMOUNT_SIGN_BOUNDARY else -value
            continue

        if value is not None and BALANCE_X0_MIN <= x0 < BALANCE_X0_MAX:
            balance = value
            continue

        description_words.append(word["text"])

    return ClassifiedRow(date, amount, balance, description_words)


def parse_hsbc_pdf(path: Path) -> list[ParsedTransaction]:
    txns: list[ParsedTransaction] = []

    capture_active = False
    current_date: str | None = None
    running_balance: Decimal | None = None
    pending_amount = Decimal("0")
    buffer: list[str] = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue

            rows_by_top = defaultdict(list)
            for word in words:
                rows_by_top[round(word["top"], 1)].append(word)

            rows = sorted(rows_by_top.values(), key=lambda r: r[0]["top"])

            for row in rows:
                row.sort(key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in row)

                if "BALANCEBROUGHTFORWARD" in text:
                    capture_active = True
                    buffer = []
                    pending_amount = Decimal("0")
                    classified = _classify_row(row)
                    if classified.balance is not None:
                        running_balance = classified.balance
                    continue

                if "BALANCECARRIEDFORWARD" in text:
                    if buffer:
                        raise ValueError(
                            f"Unterminated transaction at section close: {' '.join(buffer)!r}"
                        )
                    if pending_amount != 0:
                        raise ValueError(
                            f"Unreconciled amount at section close on {current_date}: "
                            f"{pending_amount} not matched against a printed balance"
                        )
                    capture_active = False
                    continue

                if not capture_active:
                    continue

                if text == ".":
                    continue

                classified = _classify_row(row)

                if classified.date:
                    current_date = classified.date

                buffer.extend(classified.description_words)

                if classified.amount is not None:
                    txns.append(
                        ParsedTransaction(
                            date=current_date,
                            description=" ".join(buffer),
                            amount=classified.amount,
                        )
                    )
                    buffer = []
                    pending_amount += classified.amount

                    if classified.balance is not None:
                        if running_balance is not None:
                            expected = running_balance + pending_amount
                            if expected != classified.balance:
                                raise ValueError(
                                    f"Balance mismatch on {current_date}: expected {expected}, "
                                    f"statement shows {classified.balance} "
                                    f"(last txn: {txns[-1].description!r})"
                                )
                        running_balance = classified.balance
                        pending_amount = Decimal("0")

    return txns
