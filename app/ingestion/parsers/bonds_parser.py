from app.ingestion.normalizers import is_blank, parse_date, parse_number, validate_isin
from app.ingestion.parsers.base import (
    ParsedRecord, cell, is_degenerate_row, locate_header_block, looks_like_date, looks_like_number,
    looks_like_percent, match_columns, tokenize_row,
)

COLUMN_ALIASES = {
    "isin": ["isin"],
    "status": ["status"],
    "security": ["security", "bond name", "name"],
    "maturity_date": ["maturity date", "maturity"],
    "tenor": ["tenor"],
    "coupon": ["coupon"],
    "close_price": ["closing price", "close price", "close", "yield"],
    "previous_value": ["previous value", "previous", "prev value", "prev."],
    "bids": ["bid"],
    "offers": ["offer"],
    # The real report's trailing "Bond traded" column is a volume figure (0.00 if
    # untraded that session, a real number like 52,000,000 if traded), not a flag.
    "traded_volume": ["bond traded", "traded"],
}

_ANCHOR_ALIASES = {"isin": COLUMN_ALIASES["isin"], "security": COLUMN_ALIASES["security"]}

# Trailing numeric columns in the official bond table, in fixed right-to-left order —
# used for pattern-based reconstruction because the "Status" column between ISIN and
# Security is genuinely optional (blank for newly-issued bonds, "Re-opened" for others),
# so a fixed left-to-right token position cannot be trusted; see base.py docstring.
_TRAILING_NUMERIC_FIELDS = ["close_price", "previous_value", "bids", "offers", "traded_volume"]


def _reconstruct_bond_row(row_text_tokens):
    """Pattern-based reconstruction tolerant of the optional Status column. Returns
    (fields_dict, None) or (None, reason). Never guesses: if the trailing numeric block,
    a maturity date, or a coupon percentage can't be confidently located, the row is
    rejected rather than misaligned."""
    tokens = list(row_text_tokens)
    if len(tokens) < 1 + len(_TRAILING_NUMERIC_FIELDS) + 2:  # isin + numerics + security + maturity(min)
        return None, f"too few tokens ({len(tokens)}) for a bond row"

    isin = tokens[0]
    trailing = tokens[-len(_TRAILING_NUMERIC_FIELDS):]
    if not all(looks_like_number(t) for t in trailing):
        return None, "trailing numeric fields (close/prev/bids/offers/traded) not recognized"

    middle = tokens[1:-len(_TRAILING_NUMERIC_FIELDS)]

    date_positions = [i for i, t in enumerate(middle) if looks_like_date(t)]
    if len(date_positions) != 1:
        return None, f"expected exactly one maturity-date token, found {len(date_positions)}"
    date_idx = date_positions[0]
    maturity = middle[date_idx]

    pct_positions = [i for i, t in enumerate(middle) if looks_like_percent(t)]
    coupon = None
    if pct_positions:
        # Coupon should sit immediately after the maturity date.
        coupon_idx = next((i for i in pct_positions if i > date_idx), None)
        if coupon_idx is not None:
            coupon = middle[coupon_idx]

    pre_date = middle[:date_idx]
    if len(pre_date) == 1:
        status, security = None, pre_date[0]
    elif len(pre_date) == 2:
        status, security = pre_date[0], pre_date[1]
    else:
        return None, f"could not separate status/security ({len(pre_date)} leftover token(s) before maturity date)"

    fields = {
        "isin": isin,
        "status": status,
        "security": security,
        "maturity_date": maturity,
        "coupon": coupon,
        "close_price": trailing[0],
        "previous_value": trailing[1],
        "bids": trailing[2],
        "offers": trailing[3],
        "traded_volume": trailing[4],
        "tenor": None,
    }
    return fields, None


def parse_bonds(tables, extraction_method="table_parser", bond_type="government"):
    """Returns (records, rejected)."""
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

            clean = ("security" in index_mapping or "isin" in index_mapping) and not is_degenerate_row(row)
            if clean:
                security = cell(row, index_mapping.get("security"))
                isin_raw = cell(row, index_mapping.get("isin"))
                if is_blank(security) and is_blank(isin_raw):
                    continue
                raw = {f: cell(row, idx) for f, idx in index_mapping.items()}
            else:
                raw, reason = _reconstruct_bond_row(tokenize_row(row))
                if raw is None:
                    rejected.append({"page": table.page_number, "raw": " | ".join(str(c) for c in row),
                                      "reason": reason})
                    continue

            fields = {
                "isin": raw.get("isin"),
                "status": raw.get("status"),
                "security": raw.get("security") or raw.get("isin"),
                "bond_type": bond_type,
                "maturity_date": parse_date(raw.get("maturity_date")),
                "tenor": raw.get("tenor"),
                "coupon": parse_number(raw.get("coupon")),
                "close_price": parse_number(raw.get("close_price")),
                "previous_value": parse_number(raw.get("previous_value")),
                "bids": parse_number(raw.get("bids")),
                "offers": parse_number(raw.get("offers")),
                "traded_volume": parse_number(raw.get("traded_volume")),
            }
            fields["bond_traded"] = bool(fields["traded_volume"] and fields["traded_volume"] > 0)

            record = ParsedRecord(fields, table.page_number, extraction_method,
                                   raw_text=" | ".join(str(c) for c in row))
            if fields["isin"] and not validate_isin(fields["isin"]):
                record.mark_invalid("isin")
            if is_blank(fields["maturity_date"]) and not is_blank(raw.get("maturity_date")):
                record.mark_invalid("maturity_date")
            records.append(record)

    return records, rejected
