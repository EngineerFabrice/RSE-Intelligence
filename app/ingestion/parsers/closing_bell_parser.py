import re

from app.ingestion.normalizers import is_blank, parse_integer, parse_number
from app.ingestion.parsers.base import ParsedRecord, cell, is_degenerate_row, locate_header_block, match_columns

COLUMN_ALIASES = {
    "security": ["security", "stock", "symbol"],
    "bid_quantity": ["bid quantity", "bid qty", "bid volume"],
    "bid_price": ["bid price", "bid"],
    "offer_quantity": ["offer quantity", "offer qty", "offer volume"],
    "offer_price": ["offer price", "offer"],
}

# Real official RSE reports frequently describe the closing bell as narrative prose
# instead of a table, e.g.:
#   "On KCB counter, there were outstanding bids of 11,000 shares at Frw 500 and
#    no offers."
#   "On MTNR counter, there were outstanding bids of 120,000 shares between
#    Frw 130-135 and no offers."
# This regex is deterministic (no AI/inference) — every field is a direct capture group.
_PROSE_RE = re.compile(
    r"On\s+([A-Z]{2,8})\s+counter,?\s+there\s+were\s+outstanding\s+(bids|offers)\s+of\s+"
    r"([\d,]+)\s+shares\s+(?:at|between)\s+Frw\s+([\d,]+(?:\.\d+)?)(?:\s*-\s*([\d,]+(?:\.\d+)?))?"
    r"\s+and\s+no\s+(bids|offers)",
    re.IGNORECASE,
)


def parse_closing_bell_from_tables(tables, extraction_method="table_parser"):
    """Returns (records, rejected)."""
    records = []
    rejected = []

    for table in tables:
        header_end, field_order = locate_header_block(table.rows, COLUMN_ALIASES)
        if header_end is None or "security" not in field_order:
            continue

        index_mapping = match_columns(table.header, COLUMN_ALIASES) if header_end == 1 else {}
        data_rows = table.rows[header_end:]

        for row in data_rows:
            if not any(c and str(c).strip() for c in row):
                continue
            clean = "security" in index_mapping and not is_degenerate_row(row)
            if not clean:
                # Closing-bell tables are rare/inconsistent enough in real reports that
                # we don't attempt degenerate-row reconstruction here (spec §6: clearly
                # distinguish available bids/offers from no-bid/no-offer conditions
                # rather than guess) — reject with a reason instead.
                rejected.append({"page": table.page_number, "raw": " | ".join(str(c) for c in row),
                                  "reason": "closing bell row structure not clean enough to parse safely"})
                continue

            security = cell(row, index_mapping.get("security"))
            if is_blank(security):
                continue

            bid_qty = parse_integer(cell(row, index_mapping.get("bid_quantity")))
            bid_price = parse_number(cell(row, index_mapping.get("bid_price")))
            offer_qty = parse_integer(cell(row, index_mapping.get("offer_quantity")))
            offer_price = parse_number(cell(row, index_mapping.get("offer_price")))

            has_bid = bid_price is not None
            has_offer = offer_price is not None
            status = "Active" if (has_bid or has_offer) else "No Bid / No Offer"

            fields = {
                "security": security, "bid_quantity": bid_qty, "bid_price": bid_price,
                "offer_quantity": offer_qty, "offer_price": offer_price,
                "has_bid": has_bid, "has_offer": has_offer, "status": status,
            }
            records.append(ParsedRecord(fields, table.page_number, extraction_method,
                                         raw_text=" | ".join(str(c) for c in row)))

    return records, rejected


def parse_closing_bell_from_text(pages):
    """Deterministic regex extraction from narrative closing-bell prose. Returns
    records only (no rejection tracking — a sentence that doesn't match the pattern is
    simply not closing-bell prose, not a malformed row)."""
    records = []
    for page in pages:
        for match in _PROSE_RE.finditer(page.text):
            symbol, side, qty, price_from, price_to, other_side = match.groups()
            quantity = parse_integer(qty)
            price = parse_number(price_to) if price_to else parse_number(price_from)
            if price_to:
                price = round((parse_number(price_from) + parse_number(price_to)) / 2, 4)

            is_bid = side.lower() == "bids"
            fields = {
                "security": symbol.upper(),
                "bid_quantity": quantity if is_bid else None,
                "bid_price": price if is_bid else None,
                "offer_quantity": quantity if not is_bid else None,
                "offer_price": price if not is_bid else None,
                "has_bid": is_bid,
                "has_offer": not is_bid,
                "status": "Active",
            }
            records.append(ParsedRecord(fields, page.page_number, "native_text_prose",
                                         raw_text=match.group(0)))
    return records


def parse_closing_bell(tables, pages, extraction_method="table_parser"):
    records, rejected = parse_closing_bell_from_tables(tables, extraction_method)
    if not records:
        records = parse_closing_bell_from_text(pages)
    return records, rejected
