"""Deterministic parsing and validation for financial fields (spec §8).

These functions never guess: a value that cannot be reliably parsed returns None (with
the caller responsible for flagging a validation issue) rather than a best-effort guess.
"""

import re
from datetime import date, datetime

_NUMBER_RE = re.compile(r"^\(?-?[\d,]*\.?\d*\)?%?$")

_DATE_FORMATS = [
    "%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
    "%B %d, %Y", "%d.%m.%Y", "%d %B, %Y",
]


def parse_number(raw: str):
    """Parse a financial number: thousands separators, parenthesised negatives, dashes as None."""
    if raw is None:
        return None
    text = str(raw).strip()
    if text in ("", "-", "--", "N/A", "n/a", "NA"):
        return None
    if not _NUMBER_RE.match(text):
        return None

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace("%", "").strip()
    if text in ("", "."):
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return -value if negative else value


def parse_integer(raw: str):
    value = parse_number(raw)
    if value is None:
        return None
    return int(round(value))


def parse_percentage(raw: str):
    return parse_number(raw)


def parse_currency(raw: str):
    if raw is None:
        return None
    text = str(raw).strip()
    text = re.sub(r"^(RWF|Frw|FRW|USD|\$)\s*", "", text, flags=re.IGNORECASE)
    return parse_number(text)


def parse_date(raw: str):
    """Best-effort deterministic date parse across known RSE report date formats."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def validate_isin(isin: str) -> bool:
    """ISO 6166 ISIN checksum validation (mod-97 Luhn-style)."""
    if not isin:
        return False
    isin = isin.strip().upper()
    if not re.match(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$", isin):
        return False

    converted = ""
    for ch in isin[:-1]:
        if ch.isdigit():
            converted += ch
        else:
            converted += str(ord(ch) - ord("A") + 10)

    digits = [int(d) for d in converted]
    digits.reverse()
    total = 0
    for idx, d in enumerate(digits):
        if idx % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d

    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(isin[-1])


def normalize_symbol(raw: str):
    if raw is None:
        return None
    text = str(raw).strip().upper()
    return text or None


def is_blank(raw) -> bool:
    return raw is None or str(raw).strip() in ("", "-", "--", "N/A")
