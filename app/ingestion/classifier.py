"""Stage 5 — semantic section classification (spec §7/§43).

Heuristic header matching rather than a hard-coded single-layout parser, so a report
whose formatting shifts slightly is still classified — and a report that doesn't match
the expected structure at all is flagged as a new/unknown layout rather than silently
misclassified.
"""

import re

SECTION_KEYWORDS = {
    "equities": [r"\bEQUIT(Y|IES)\b", r"\bSTOCK\b", r"\bSHARE PRICE", r"\bLISTED SECURITIES"],
    "bonds": [r"\bGOVERNMENT BOND", r"\bCORPORATE BOND", r"\bBOND MARKET", r"\bBONDS\b"],
    # NOTE: must NOT match the "Bond traded" (Yes/No) *column header* that appears
    # inside the Government/Corporate Bonds tables — real reports were observed
    # misclassifying those bond pages as an (nonexistent) extra bond-trades section
    # because "\bBOND TRADE" (no trailing boundary) matches as a prefix of "traded".
    # Requiring a trailing word boundary/plural fixes it without weakening detection of
    # genuine "BOND TRADES" / "BONDS TRADED" section headings.
    "bond_trades": [r"\bBOND TRADES\b", r"\bBONDS TRADED\b", r"\bBOND TRADING\b"],
    "indices": [r"\bINDEX\b", r"\bINDICES\b", r"\bRSI\b", r"\bALSI\b"],
    "market_statistics": [r"\bMARKET STATISTIC", r"\bTRADING STATISTIC", r"\bMARKET SUMMARY",
                           r"\bMARKET OVERVIEW", r"\bMARKET CAPITALI[SZ]ATION"],
    "exchange_rates": [r"\bEXCHANGE RATE", r"\bFOREIGN EXCHANGE", r"\bFX RATE"],
    "closing_bell": [r"\bCLOSING BELL", r"\bORDER BOOK", r"\bBIDS? AND OFFERS?"],
}

# Sections that a well-formed RSE report is expected to contain; used to score layout confidence.
CORE_SECTIONS = ["equities", "market_statistics", "exchange_rates"]

_COMPILED = {
    section: [re.compile(p, re.IGNORECASE) for p in patterns]
    for section, patterns in SECTION_KEYWORDS.items()
}

_DATE_LINE_RE = re.compile(
    r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})|(\d{4}-\d{2}-\d{2})|(\d{1,2}/\d{1,2}/\d{4})"
)


class Classification:
    def __init__(self):
        self.sections = {}  # section_name -> list[page_number]
        self.layout_confidence = 0.0
        self.is_new_format = False
        self.detected_report_date_text = None


def classify_document(pages) -> Classification:
    result = Classification()

    for page in pages:
        text_upper = page.text.upper()
        for section, patterns in _COMPILED.items():
            if any(p.search(text_upper) for p in patterns):
                result.sections.setdefault(section, []).append(page.page_number)

        if result.detected_report_date_text is None:
            match = _DATE_LINE_RE.search(page.text)
            if match:
                result.detected_report_date_text = match.group(0)

    found_core = sum(1 for s in CORE_SECTIONS if s in result.sections)
    result.layout_confidence = found_core / len(CORE_SECTIONS) if CORE_SECTIONS else 0.0
    result.is_new_format = result.layout_confidence < 0.5

    return result


def pages_for_section(classification: Classification, section: str, pages):
    page_numbers = set(classification.sections.get(section, []))
    return [p for p in pages if p.page_number in page_numbers]


def tables_for_pages(tables, page_numbers):
    page_numbers = set(page_numbers)
    return [t for t in tables if t.page_number in page_numbers]
