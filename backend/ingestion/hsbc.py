from decimal import Decimal
from pathlib import Path

import pdfplumber
from common import ParsedTransaction


def parse_hsbc_pdf(path: Path) -> list[ParsedTransaction]:
    txns = []
    with pdfplumber.open(path) as pdf:
        p0 = pdf.pages[0]
        im = p0.to_image()
        im.draw_rects(p0.extract_words())
        im.show()
        tables = []
        for p in pdf.pages:
            print(p.extract_text())
    return txns
