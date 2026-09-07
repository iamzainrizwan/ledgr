import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pdfplumber
from common import ParsedTransaction
from sqlalchemy.sql.functions import current_date


def parse_hsbc_pdf(path: Path) -> list[ParsedTransaction]:
    txns = []
    with pdfplumber.open(path) as pdf:
        p0 = pdf.pages[0]
        im = p0.to_image()
        im.draw_rects(p0.extract_words())
        im.show()
        capture_active = False
        starts_with_number = re.compile(r"^\d")
        for p in pdf.pages:
            text = p.extract_text()
            if not text:
                continue
            for line in text.split("\n"):
                line = line.strip()
                if "BALANCEBROUGHTFORWARD" in line:
                    capture_active = True
                    line_strip = line.strip()
                    if starts_with_number.match(line_strip):
                        parts = line_strip.split(maxsplit=3)
                        current_date = " ".join(parts[:3])
                    continue
                if "BALANCECARRIEDFORWARD" in line:
                    capture_active = False
                    continue
                if capture_active:
                    line_strip = line.strip()
                    if not line_strip:
                        continue
                    if starts_with_number.match(line_strip):
                        parts = line_strip.split(maxsplit=3)
                        current_date = " ".join(parts[:3])
                        remaining_text = " ".join(parts[3:])
                        txns.append({"Date": current_date, "Raw_Data": remaining_text})
                    else:
                        txns.append(
                            {
                                "Date": current_date if current_date else "Unknown",
                                "Raw_Data": line_strip,
                            }
                        )

    df = pd.DataFrame(txns)
    print(df)
    return txns
