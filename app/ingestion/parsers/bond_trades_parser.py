from app.ingestion.normalizers import is_blank, parse_date, parse_integer, parse_number
from app.ingestion.parsers.base import (
    ParsedRecord, cell, is_degenerate_row, locate_header_block, match_columns, resolve_row_fields,
)

COLUMN_ALIASES = {
    "trade_date": ["trade date", "trading date", "date"],
    "isin": ["isin"],
    "security": ["security", "bond"],
    "price_yield": ["price", "yield"],
    "volume": ["volume", "quantity"],
    "value": ["value"],
    "number_of_trades": ["number of trades", "no. of deals", "deals", "number of deals"],
}

# number_of_trades is frequently absent from the printed blotter, so the canonical
# fallback used for positional reconstruction excludes it (spec §3 "BONDS TRADES" lists
# it as supplementary, not a core field).
CANONICAL_FIELD_ORDER = ["trade_date", "isin", "security", "price_yield", "volume", "value"]

_ANCHOR_ALIASES = {"isin": COLUMN_ALIASES["isin"], "security": COLUMN_ALIASES["security"]}


def parse_bond_trades(tables, extraction_method="table_parser"):
    """Returns (records, rejected)."""
    records = []
    rejected = []

    for table in tables:
        header_end, alias_field_order = locate_header_block(table.rows, COLUMN_ALIASES)
        anchor_header_end, anchors_found = locate_header_block(table.rows, _ANCHOR_ALIASES, min_match_ratio=1.0)
        if header_end is None or not anchors_found:
            continue
        header_end = max(header_end, anchor_header_end)

        index_mapping = match_columns(table.header, COLUMN_ALIASES) if header_end == 1 else {}
        data_rows = table.rows[header_end:]

        for row in data_rows:
            if not any(c and str(c).strip() for c in row):
                continue

            clean = ("security" in index_mapping or "isin" in index_mapping) and not is_degenerate_row(row)
            if clean:
                security = cell(row, index_mapping.get("security"))
                isin_raw = cell(row, index_mapping.get("isin"))
                if is_blank(security) and is_blank(isin_raw):
                    continue
                raw = {f: cell(row, idx) for f, idx in index_mapping.items()}
            else:
                raw, reason = resolve_row_fields(row, CANONICAL_FIELD_ORDER)
                if raw is None:
                    raw, reason = resolve_row_fields(row, alias_field_order)
                if raw is None:
                    rejected.append({"page": table.page_number, "raw": " | ".join(str(c) for c in row),
                                      "reason": reason})
                    continue

            fields = {
                "trade_date": parse_date(raw.get("trade_date")),
                "isin": raw.get("isin"),
                "security": raw.get("security"),
                "price_yield": parse_number(raw.get("price_yield")),
                "volume": parse_integer(raw.get("volume")),
                "value": parse_number(raw.get("value")),
                "number_of_trades": parse_integer(raw.get("number_of_trades")),
            }
            records.append(ParsedRecord(fields, table.page_number, extraction_method,
                                         raw_text=" | ".join(str(c) for c in row)))

    return records, rejected
