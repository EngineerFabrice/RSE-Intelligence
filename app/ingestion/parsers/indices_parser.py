import re

from app.ingestion.normalizers import parse_number
from app.ingestion.parsers.base import ParsedRecord, cell, is_degenerate_row, locate_header_block, match_columns

COLUMN_ALIASES = {
    # NOTE: "indices" (the real header word, plural) is NOT a substring of "index" —
    # "indices" is spelled ind-ices, not index+es — so both forms must be listed
    # explicitly or the real "INDICES" table header never matches at all.
    "index_name": ["index", "indices"],
    "current_value": ["current value", "current", "today", "close"],
    "previous_value": ["previous value", "previous"],
    "change": ["points", "change"],
    "percentage_change": ["% change", "percentage change", "change %"],
}

# "index_name" alone is too generic a match (e.g. a chart caption like "RWANDA SHARE
# INDEX" contains "index" as a substring and was observed, in a real uploaded report,
# to make a completely unrelated table — the bonds table — get misread as index data).
# Requiring at least one numeric anchor column too prevents that class of false match.
_ANCHOR_ALIASES = {"index_name": COLUMN_ALIASES["index_name"], "current_value": COLUMN_ALIASES["current_value"]}

KNOWN_INDICES = ("RSI", "ALSI")
_PLAUSIBLE_INDEX_NAME_RE = re.compile(r"^[A-Z]{2,8}$")

# Two known real-world formats for an index line in narrative/near-table text:
#  (a) "RSI: 132.45 (1.20%)"                          -> a single current value + %
#  (b) "RSI 214.08 214.08 +0.00 +0.00" (no "%" sign)  -> Previous / Today / Points / %
# (b) is the collapsed real-report layout (Previous / Today / Points-change /
# %-change); "Today" (not the first number, which is "Previous") is the current value.
# The two are disambiguated by the literal "%" sign, which only ever appears in (a).
_SINGLE_WITH_PERCENT_RE = re.compile(
    r"\b(RSI|ALSI)\b[:\s]+\(?(-?[\d,]+\.?\d*)\)?\s*\(?(-?[\d.]+)%\)?", re.IGNORECASE
)
_MULTI_NUMBER_RE = re.compile(
    r"\b(RSI|ALSI)\b\s+\(?(-?[\d,]+\.?\d*)\)?\s+\(?(-?[\d,]+\.?\d*)\)?"
    r"(?:\s+\(?(-?[\d,]+\.?\d*)\)?)?(?:\s+\(?(-?[\d,]+\.?\d*)\)?)?",
    re.IGNORECASE,
)


def _plausible_index_name(name: str) -> bool:
    name = (name or "").strip().upper()
    return name in KNOWN_INDICES or bool(_PLAUSIBLE_INDEX_NAME_RE.match(name))


def parse_indices_from_tables(tables, extraction_method="table_parser"):
    records = []
    rejected = []

    for table in tables:
        header_end, _ = locate_header_block(table.rows, COLUMN_ALIASES)
        anchor_header_end, anchors_found = locate_header_block(table.rows, _ANCHOR_ALIASES, min_match_ratio=1.0)
        if header_end is None or not anchors_found:
            continue
        header_end = max(header_end, anchor_header_end)

        index_mapping = match_columns(table.header, COLUMN_ALIASES) if header_end == 1 else {}
        data_rows = table.rows[header_end:]

        for row in data_rows:
            if not any(c and str(c).strip() for c in row):
                continue
            clean = "index_name" in index_mapping and not is_degenerate_row(row)
            if not clean:
                rejected.append({"page": table.page_number, "raw": " | ".join(str(c) for c in row),
                                  "reason": "index table row structure not clean enough to parse safely"})
                continue

            name = cell(row, index_mapping.get("index_name"))
            if not name or not _plausible_index_name(name):
                continue

            fields = {
                "index_name": name.strip().upper(),
                "current_value": parse_number(cell(row, index_mapping.get("current_value"))),
                "previous_value": parse_number(cell(row, index_mapping.get("previous_value"))),
                "change": parse_number(cell(row, index_mapping.get("change"))),
                "percentage_change": parse_number(cell(row, index_mapping.get("percentage_change"))),
            }
            records.append(ParsedRecord(fields, table.page_number, extraction_method,
                                         raw_text=" | ".join(str(c) for c in row)))

    return records, rejected


def parse_indices_from_text(pages, extraction_method="native_text"):
    records = []
    for page in pages:
        claimed_spans = []

        for match in _SINGLE_WITH_PERCENT_RE.finditer(page.text):
            name, current, pct_change = match.groups()
            fields = {
                "index_name": name.upper(),
                "current_value": parse_number(current),
                "previous_value": None,
                "change": None,
                "percentage_change": parse_number(pct_change) if pct_change else None,
            }
            records.append(ParsedRecord(fields, page.page_number, extraction_method, raw_text=match.group(0)))
            claimed_spans.append(match.span())

        for match in _MULTI_NUMBER_RE.finditer(page.text):
            if any(start <= match.start() < end for start, end in claimed_spans):
                continue  # already captured by the more specific single+percent pattern
            name, previous, today, points_change, pct_change = match.groups()
            fields = {
                "index_name": name.upper(),
                "current_value": parse_number(today),
                "previous_value": parse_number(previous),
                "change": parse_number(points_change) if points_change else None,
                "percentage_change": parse_number(pct_change) if pct_change else None,
            }
            records.append(ParsedRecord(fields, page.page_number, extraction_method, raw_text=match.group(0)))
    return records


def parse_indices(tables, pages, extraction_method="table_parser"):
    """Returns (records, rejected)."""
    records, rejected = parse_indices_from_tables(tables, extraction_method)
    found_names = {r.fields["index_name"] for r in records}
    for r in parse_indices_from_text(pages):
        if r.fields["index_name"] not in found_names:
            records.append(r)
            found_names.add(r.fields["index_name"])
    return records, rejected
