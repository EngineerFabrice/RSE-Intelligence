"""Stage 3 — layout-aware table extraction (spec §7).

Real official RSE reports are frequently laid out with whitespace/positional alignment
rather than drawn grid lines. pdfplumber's default line-based table detector handles
that unreliably in two specific, evidence-based ways (found by processing real uploaded
RSE reports — see app/ingestion/parsers/base.py for how downstream parsers compensate):

1. One logical table is sometimes split into several small "tables" on the same page
   (a stray label lands in its own 1-row table). `extract_tables()` merges same-page
   fragments back into one table so a parser sees the whole thing.
2. Even within one detected table, column boundaries can fail to be found at all, so an
   entire row's text collapses into a single cell. That case is handled by the
   degenerate-row reconstruction helpers in `parsers/base.py`, not here — this module
   only guarantees rows/pages are grouped sensibly.
"""

import logging

logger = logging.getLogger("rse_intelligence.ingestion")


class ExtractedTable:
    def __init__(self, page_number: int, rows: list):
        self.page_number = page_number
        self.rows = rows  # list[list[str]]

    @property
    def header(self):
        return self.rows[0] if self.rows else []

    @property
    def data_rows(self):
        return self.rows[1:] if len(self.rows) > 1 else []


_FRAGMENT_MAX_ROWS = 2  # a table this small is almost certainly a stray header-label
                         # fragment (e.g. a lone ['Closing'] "table"), not a real table


def _looks_like_fragment(table) -> bool:
    """A table is treated as a stray fragment (candidate for merging into its neighbor)
    when it's tiny (<= _FRAGMENT_MAX_ROWS rows) — almost always a scattered header-label
    leftover (e.g. a lone ['Closing'] "table").

    A broader "every row has at most one populated cell" rule was tried and reverted:
    on documents where pdfplumber loses column structure for an entire page, several
    genuinely distinct sections (e.g. indices, market statistics, exchange rates) can
    each independently degenerate to single-cell rows, and that broader rule merged all
    of them into one table — which made section header detection fail entirely
    (real regression, caught by reprocessing actual uploaded reports; see the
    remediation notes in app/ingestion/pipeline.py). Row-count is a safer, evidence-
    validated signal on its own.
    """
    return len(table.rows) <= _FRAGMENT_MAX_ROWS


def _merge_page_fragments(page_number: int, raw_tables: list) -> list:
    """Fold stray fragment tables (see `_looks_like_fragment`) into the next real table
    on the same page, in order — without touching genuinely separate, well-formed tables
    that happen to share a page (a very common, legitimate layout that must NOT be
    merged together).

    Returns a list (usually of length 1, but preserves multiple real tables on one page
    rather than force-merging them).
    """
    if len(raw_tables) == 1:
        return raw_tables

    merged = []
    pending_fragment_rows = []
    for t in raw_tables:
        if _looks_like_fragment(t):
            pending_fragment_rows.extend(t.rows)
            continue
        merged.append(ExtractedTable(page_number, pending_fragment_rows + t.rows))
        pending_fragment_rows = []

    if pending_fragment_rows:
        # Trailing fragments with no real table to attach to on this page — keep them
        # as their own (likely unparseable, and that's fine) table rather than losing
        # the rows outright.
        merged.append(ExtractedTable(page_number, pending_fragment_rows))

    return merged or raw_tables


def extract_tables(pdf_path: str):
    """Returns list[ExtractedTable], at most one per page (fragments merged).
    Never raises — an extraction failure yields an empty list so the pipeline can
    continue with text-only parsing."""
    import pdfplumber

    tables_by_page = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_number = i + 1
                for raw_table in page.extract_tables():
                    cleaned = [
                        [(cell or "").strip() for cell in row]
                        for row in raw_table
                        if any((cell or "").strip() for cell in row)
                    ]
                    if cleaned:
                        tables_by_page.setdefault(page_number, []).append(
                            ExtractedTable(page_number, cleaned)
                        )
    except Exception:
        logger.exception("Table extraction failed for %s", pdf_path)
        return []

    result = []
    for page_number, raw_tables in sorted(tables_by_page.items()):
        result.extend(_merge_page_fragments(page_number, raw_tables))
    return result
