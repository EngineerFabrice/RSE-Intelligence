"""Shared helpers for section parsers: flexible column mapping and record lineage.

Column headers in official RSE reports can shift wording between issues, so mapping is
alias/substring based (spec §43) rather than tied to one exact layout, and never tied to
sample data.

Two additional, evidence-based helpers exist here because of what real uploaded RSE
reports actually look like once run through the pipeline:

- `locate_header_block()` — a real report's column labels are not reliably on row 0.
  They can wrap across several rows, or (after `table_extraction.py` merges same-page
  table fragments) be scattered across what used to be separate tiny tables. This scans
  forward accumulating row text until enough known aliases have been seen, instead of
  assuming row 0 is the header.
- `is_degenerate_row()` / `tokenize_row()` / `reconstruct_positional()` — when a report
  has no drawn grid lines, pdfplumber's column-boundary detection can fail entirely and
  an entire row's values collapse into a single cell (e.g. one string
  "RW000A1JCYA5 BOK 661 330 660 660 660 660 +0.00 21,600 14,256,000" instead of 11
  separate cells). `reconstruct_positional()` only ever re-splits such a row when the
  resulting whitespace-token count matches the header's field count *exactly* — if it
  doesn't match (e.g. an optional column is blank for that row), it refuses to guess and
  returns None, leaving that row to be rejected with a reason rather than silently
  misaligned. Section-specific parsers that need to tolerate optional missing columns
  (see `bonds_parser.py`) do their own type-pattern reconstruction instead.
"""

import re

NUMBER_TOKEN_RE = re.compile(r"^\(?-?[\d,]+\.?\d*\)?%?$")
PERCENT_TOKEN_RE = re.compile(r"^\(?-?[\d.]+%\)?$")
DATE_TOKEN_RE = re.compile(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}$")


class ParsedRecord:
    def __init__(self, fields: dict, source_page: int, extraction_method: str = "table_parser",
                 raw_text: str = None):
        self.fields = fields
        self.field_valid = {name: True for name in fields}
        self.field_source_text = {}
        self.source_page = source_page
        self.extraction_method = extraction_method
        self.was_ocr = extraction_method == "ocr"
        self.raw_text = raw_text

    def mark_invalid(self, field_name):
        self.field_valid[field_name] = False


def match_columns(header_row, column_aliases: dict):
    """Map field_name -> column index using longest-alias-first substring matching.

    Each field in `column_aliases` maps to a list of acceptable header substrings
    (case-insensitive). A header cell is assigned to at most one field, preferring the
    longest/most specific alias match so e.g. "12M High" isn't swallowed by "High".
    """
    candidates = []
    for field, aliases in column_aliases.items():
        for alias in aliases:
            for idx, cell in enumerate(header_row):
                if alias.lower() in (cell or "").lower():
                    candidates.append((len(alias), field, idx))

    candidates.sort(key=lambda c: -c[0])

    assigned_fields = set()
    assigned_columns = set()
    mapping = {}
    for _, field, idx in candidates:
        if field in assigned_fields or idx in assigned_columns:
            continue
        mapping[field] = idx
        assigned_fields.add(field)
        assigned_columns.add(idx)

    return mapping


def cell(row, idx):
    if idx is None or idx >= len(row):
        return None
    value = row[idx]
    return value.strip() if isinstance(value, str) else value


def looks_like_header(row) -> bool:
    """A very small heuristic: header rows are mostly non-numeric text."""
    text_cells = [c for c in row if c and not c.replace(",", "").replace(".", "").replace("-", "").isdigit()]
    return len(text_cells) >= max(1, len(row) // 2)


def row_text(row) -> str:
    return " ".join(str(c).strip() for c in row if c and str(c).strip())


def tokenize_row(row) -> list:
    return row_text(row).split()


def is_degenerate_row(row) -> bool:
    """True when a row's values have collapsed into one or two cells instead of being
    split per column — the signature of pdfplumber failing to find column boundaries on
    a borderless real-world table."""
    non_empty = [c for c in row if c and str(c).strip()]
    return len(row) > 2 and len(non_empty) <= 2


def looks_like_number(token: str) -> bool:
    return bool(NUMBER_TOKEN_RE.match(token))


def looks_like_percent(token: str) -> bool:
    return bool(PERCENT_TOKEN_RE.match(token))


def looks_like_date(token: str) -> bool:
    return bool(DATE_TOKEN_RE.match(token))


def locate_header_block(rows, column_aliases: dict, min_match_ratio: float = 0.5, max_scan_rows: int = 6):
    """Find where a table's header ends by accumulating row text (rather than assuming
    row 0 alone is the header) until enough known column aliases have appeared.

    Returns (header_end_index, field_order): `header_end_index` is the first data-row
    index (rows[:header_end_index] are all header), and `field_order` is the list of
    field names in left-to-right order, inferred from where each alias was first seen in
    the accumulated header text. Returns (None, []) if no header could be located.
    """
    if not rows or not column_aliases:
        return None, []

    accumulated = ""
    for i in range(min(max_scan_rows, len(rows))):
        accumulated += " " + row_text(rows[i])
        lowered = accumulated.lower()

        offsets = {}
        for field, aliases in column_aliases.items():
            best = None
            for alias in aliases:
                idx = lowered.find(alias.lower())
                if idx != -1 and (best is None or idx < best):
                    best = idx
            if best is not None:
                offsets[field] = best

        if len(offsets) / len(column_aliases) >= min_match_ratio:
            field_order = sorted(offsets.keys(), key=lambda f: offsets[f])
            return i + 1, field_order

    return None, []


def reconstruct_positional(row, field_order: list):
    """Safely re-split a degenerate row into fields, but ONLY when the row's whitespace-
    token count matches `field_order` exactly — with no ambiguity about which token maps
    to which field. Returns a {field: raw_token} dict, or None if the counts don't match
    (the caller must not guess in that case; reject the row with a reason instead)."""
    tokens = tokenize_row(row)
    if len(tokens) != len(field_order):
        return None
    return dict(zip(field_order, tokens))


def resolve_row_fields(row, field_order: list, index_mapping: dict = None):
    """Resolve one table row into {field: raw_string} for a parser to type-convert.

    Tries, in order:
    1. `index_mapping` (from `match_columns` against a clean single-row header) — the
       normal case for well-formed grid tables, including ones with legitimately blank
       optional cells.
    2. Exact positional reconstruction via `reconstruct_positional` — for degenerate
       rows (pdfplumber collapsed the row into one cell) or when there is no usable
       index mapping (multi-row/fragmented header).

    Returns (values, None) on success or (None, reason) on failure — a row that can't be
    confidently aligned is never guessed at, only rejected with an explanation.
    """
    if index_mapping and not is_degenerate_row(row):
        return {f: cell(row, idx) for f, idx in index_mapping.items()}, None

    reconstructed = reconstruct_positional(row, field_order)
    if reconstructed is not None:
        return reconstructed, None

    non_empty = [c for c in row if c and str(c).strip()]
    tokens = tokenize_row(row)
    return None, (f"row could not be aligned to {len(field_order)} expected fields "
                   f"(found {len(non_empty)} populated cell(s) / {len(tokens)} token(s))")
