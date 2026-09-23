from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pdfplumber
from backend.ingestion.common import (
    ParsedStatement,
    ParsedTransaction,
    StatementParseError,
    self_validate,
)

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
        return Decimal(text.replace(",", "").replace("£", ""))
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


def _extract_account_summary(words: list) -> tuple[Decimal | None, Decimal | None]:
    SUMMARY_VALUE_X0_MIN = 500
    SUMMARY_VALUE_X0_MAX = 550
    candidates = [
        w for w in words if SUMMARY_VALUE_X0_MIN <= w["x0"] <= SUMMARY_VALUE_X0_MAX
    ]
    opening_label = next((w for w in words if w["text"] == "OpeningBalance"), None)
    closing_label = next((w for w in words if w["text"] == "ClosingBalance"), None)
    if opening_label is None or closing_label is None:
        raise StatementParseError("No account summary values found.")
    opening_word = min(candidates, key=lambda w: abs(w["top"] - opening_label["top"]))
    closing_word = min(candidates, key=lambda w: abs(w["top"] - closing_label["top"]))
    return (_decimal(opening_word["text"]), _decimal(closing_word["text"]))


def parse_hsbc_pdf(path: Path) -> ParsedStatement:
    txns: list[ParsedTransaction] = []

    capture_active = False
    current_date: str | None = None
    closing_balance: Decimal | None = None
    opening_balance: Decimal | None = None
    buffer: list[str] = []

    with pdfplumber.open(path) as pdf:
        opening_balance, closing_balance = _extract_account_summary(
            pdf.pages[0].extract_words()
        )

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
                    continue

                if "BALANCECARRIEDFORWARD" in text:
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
                    if current_date is None:
                        raise StatementParseError(
                            f"No date found for transaction {' '.join(buffer)}"
                        )

                    txns.append(
                        ParsedTransaction(
                            date=current_date,
                            description=" ".join(buffer),
                            amount=classified.amount,
                        )
                    )
                    buffer = []

    if opening_balance is None or closing_balance is None:
        raise StatementParseError("No opening or closing balance found.")
    self_validate(
        txns, opening_balance=opening_balance, closing_balance=closing_balance
    )
    statement: ParsedStatement = ParsedStatement(
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        transactions=txns,
    )

    return statement
