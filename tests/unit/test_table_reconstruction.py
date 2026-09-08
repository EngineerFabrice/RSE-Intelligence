"""Regression tests for the degenerate-row / multi-row-header handling added after
auditing real uploaded RSE reports (see app/ingestion/parsers/base.py docstring)."""

from app.ingestion.parsers.base import (
    is_degenerate_row, locate_header_block, reconstruct_positional, resolve_row_fields,
)

ALIASES = {
    "isin": ["isin"],
    "symbol": ["security", "stock"],
    "closing_price": ["closing price", "closing"],
    "volume": ["volume"],
}


def test_is_degenerate_row_detects_collapsed_cells():
    assert is_degenerate_row(["RW00 BOK 660 660 21600", "", "", "", ""]) is True


def test_is_degenerate_row_false_for_clean_row():
    assert is_degenerate_row(["RW00", "BOK", "660", "660", "21600"]) is False


def test_locate_header_block_single_row():
    rows = [
        ["ISIN", "Stock", "Closing Price", "Volume"],
        ["RW00", "BOK", "660", "21600"],
    ]
    header_end, field_order = locate_header_block(rows, ALIASES)
    assert header_end == 1
    assert field_order == ["isin", "symbol", "closing_price", "volume"]


def test_locate_header_block_multi_row_header():
    # Mirrors a real report: header labels spread across several rows before data.
    # With this minimal 4-field alias set, 2/4 (the 50% default ratio) is already met
    # by row index 2 ("Stock" + "Closing"), before the ISIN-CODE row — this is exactly
    # why parsers pair this with a *stricter* 100%-ratio anchor pass and take
    # whichever boundary is further along (see equities_parser.py / bonds_parser.py),
    # rather than relying on locate_header_block alone to find the true full boundary.
    rows = [
        ["", "Past 12", "Today's"],
        ["", "months", "session"],
        ["", "Stock", "", "Closing"],
        ["ISIN-CODE", "", "High Low", "Volume"],
        ["RW00 BOK 660 660 21600", "", "", ""],
    ]
    header_end, field_order = locate_header_block(rows, ALIASES)
    assert header_end == 3
    assert "symbol" in field_order and "closing_price" in field_order

    # The full alias set (all 4 fields) isn't satisfied until the ISIN-CODE row (index
    # 3) is included — demonstrating the anchor-widening pattern parsers rely on.
    full_header_end, full_field_order = locate_header_block(rows, ALIASES, min_match_ratio=1.0)
    assert full_header_end == 4
    assert set(full_field_order) == {"isin", "symbol", "closing_price", "volume"}


def test_locate_header_block_returns_none_when_no_match():
    rows = [["Totally", "Unrelated", "Content"]]
    header_end, field_order = locate_header_block(rows, ALIASES)
    assert header_end is None
    assert field_order == []


def test_reconstruct_positional_exact_match():
    field_order = ["isin", "symbol", "closing_price", "volume"]
    row = ["RW00 BOK 660 21600", "", "", ""]
    result = reconstruct_positional(row, field_order)
    assert result == {"isin": "RW00", "symbol": "BOK", "closing_price": "660", "volume": "21600"}


def test_reconstruct_positional_refuses_to_guess_on_count_mismatch():
    field_order = ["isin", "symbol", "closing_price", "volume"]
    row = ["RW00 BOK 660", "", "", ""]  # only 3 tokens for 4 fields
    assert reconstruct_positional(row, field_order) is None


def test_resolve_row_fields_prefers_clean_index_mapping():
    field_order = ["isin", "symbol", "closing_price", "volume"]
    index_mapping = {"isin": 0, "symbol": 1, "closing_price": 2, "volume": 3}
    row = ["RW00", "BOK", "660", "21600"]
    values, reason = resolve_row_fields(row, field_order, index_mapping)
    assert reason is None
    assert values == {"isin": "RW00", "symbol": "BOK", "closing_price": "660", "volume": "21600"}


def test_resolve_row_fields_falls_back_to_reconstruction_for_degenerate_row():
    field_order = ["isin", "symbol", "closing_price", "volume"]
    index_mapping = {"isin": 0, "symbol": 1, "closing_price": 2, "volume": 3}
    row = ["RW00 BOK 660 21600", "", "", ""]  # degenerate despite a clean index_mapping
    values, reason = resolve_row_fields(row, field_order, index_mapping)
    assert reason is None
    assert values["isin"] == "RW00"


def test_resolve_row_fields_rejects_with_reason_when_unalignable():
    field_order = ["isin", "symbol", "closing_price", "volume"]
    row = ["RW00 BOK 660", "", "", ""]  # degenerate, wrong token count
    values, reason = resolve_row_fields(row, field_order, index_mapping=None)
    assert values is None
    assert "expected 4" in reason or "4 expected" in reason
