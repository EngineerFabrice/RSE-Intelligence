from app.ingestion.normalizers import normalize_symbol, parse_integer, parse_number, validate_isin
from app.ingestion.parsers.base import (
    ParsedRecord, cell, is_degenerate_row, locate_header_block, match_columns, resolve_row_fields,
)

COLUMN_ALIASES = {
    "isin": ["isin"],
    "symbol": ["security symbol", "stock symbol", "symbol", "security", "stock", "ticker"],
    "security_name": ["security name", "company name", "name"],
    "high_12m": ["12m high", "12-month high", "12 month high", "12 months high", "year high",
                 "52 week high", "52wk high"],
    "low_12m": ["12m low", "12-month low", "12 month low", "12 months low", "year low",
                "52 week low", "52wk low"],
    "today_high": ["today's high", "today's session high", "today high", "day high"],
    "today_low": ["today's low", "today's session low", "today low", "day low"],
    "closing_price": ["closing price", "close price", "closing"],
    "previous_close": ["previous closing", "prev closing", "previous close", "prev close", "prev."],
    "change": ["change"],
    "volume": ["volume", "shares traded", "quantity traded", "quantity"],
    "value_turnover": ["value/turnover", "turnover", "value"],
}

# The official RSE equities table has a known, documented column sequence (platform
# spec §3 "STOCK" sheet). When a table's header can't be cleanly split into per-column
# cells (see base.py docstring — real reports without ruling lines collapse a whole row
# into one cell), this canonical order is used to positionally reconstruct rows instead
# of guessing: "High"/"Low" appear twice in the real header (once for the 12-month
# range, once for today's session) with no distinguishing text, so free-text alias
# matching alone cannot tell them apart — only their documented position can.
CANONICAL_FIELD_ORDER = [
    "isin", "symbol", "high_12m", "low_12m", "today_high", "today_low",
    "closing_price", "previous_close", "change", "volume", "value_turnover",
]

# A handful of unambiguous aliases used only to confirm a table actually is the
# equities section before attempting canonical positional reconstruction.
_ANCHOR_ALIASES = {
    "isin": COLUMN_ALIASES["isin"],
    "closing_price": COLUMN_ALIASES["closing_price"],
    "volume": COLUMN_ALIASES["volume"],
}


def parse_equities(tables, extraction_method="table_parser"):
    """Returns (records, rejected) — rejected is a list of {page, raw, reason} dicts for
    diagnostics (spec §5/§7): a malformed row is reported, never silently dropped."""
    records = []
    rejected = []

    for table in tables:
        header_end, alias_field_order = locate_header_block(table.rows, COLUMN_ALIASES)
        # A full 100%-anchor pass often needs to scan further than the 50%-ratio pass
        # above (e.g. the ISIN-CODE label can be the last header cell to appear across
        # several wrapped header rows) — use whichever boundary is further along so a
        # trailing header fragment is never mistaken for the first data row.
        anchor_header_end, anchors_found = locate_header_block(table.rows, _ANCHOR_ALIASES, min_match_ratio=1.0)
        if header_end is None or not anchors_found:
            continue  # not an equities table
        header_end = max(header_end, anchor_header_end)

        # Clean single-row header -> classic index-based mapping still works and is
        # preferred (handles legitimately blank optional cells correctly).
        index_mapping = match_columns(table.header, COLUMN_ALIASES) if header_end == 1 else {}

        data_rows = table.rows[header_end:]
        for row in data_rows:
            if not any(c and str(c).strip() for c in row):
                continue

            has_clean_mapping = ("symbol" in index_mapping or "isin" in index_mapping) and not is_degenerate_row(row)

            if has_clean_mapping:
                raw = {f: cell(row, idx) for f, idx in index_mapping.items()}
            else:
                field_order = CANONICAL_FIELD_ORDER
                raw, reason = resolve_row_fields(row, field_order, index_mapping=None)
                if raw is None:
                    # Also allow the alias-derived order (covers reports whose header
                    # genuinely differs from the canonical layout).
                    raw, reason = resolve_row_fields(row, alias_field_order, index_mapping=None)

            if raw is None:
                rejected.append({"page": table.page_number, "raw": " | ".join(str(c) for c in row),
                                  "reason": reason or "unrecognized row structure"})
                continue

            symbol = normalize_symbol(raw.get("symbol"))
            isin_raw = raw.get("isin")
            if not symbol and not isin_raw:
                rejected.append({"page": table.page_number, "raw": " | ".join(str(c) for c in row),
                                  "reason": "no symbol or ISIN found in row"})
                continue

            fields = {
                "isin": isin_raw,
                "symbol": symbol or (isin_raw or "").strip(),
                "security_name": raw.get("security_name"),
                "high_12m": parse_number(raw.get("high_12m")),
                "low_12m": parse_number(raw.get("low_12m")),
                "today_high": parse_number(raw.get("today_high")),
                "today_low": parse_number(raw.get("today_low")),
                "closing_price": parse_number(raw.get("closing_price")),
                "previous_close": parse_number(raw.get("previous_close")),
                "change": parse_number(raw.get("change")),
                "volume": parse_integer(raw.get("volume")),
                "value_turnover": parse_number(raw.get("value_turnover")),
            }

            closing = fields["closing_price"]
            prev = fields["previous_close"]
            if fields["change"] is None and closing is not None and prev is not None:
                fields["change"] = round(closing - prev, 4)
            fields["change_percent"] = (
                round((fields["change"] / prev) * 100, 4) if fields["change"] is not None and prev else None
            )

            record = ParsedRecord(fields, table.page_number, extraction_method,
                                   raw_text=" | ".join(str(c) for c in row))
            if fields["isin"] and not validate_isin(fields["isin"]):
                record.mark_invalid("isin")
            if not fields["symbol"]:
                record.mark_invalid("symbol")
            records.append(record)

    return records, rejected
