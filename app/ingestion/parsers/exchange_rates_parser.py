from app.ingestion.normalizers import is_blank, parse_number
from app.ingestion.parsers.base import (
    cell, is_degenerate_row, locate_header_block, match_columns, resolve_row_fields, ParsedRecord,
)

COLUMN_ALIASES = {
    "currency": ["currency"],
    "buy_rate": ["buying rate", "buy rate", "buy"],
    "sell_rate": ["selling rate", "sell rate", "sell"],
    "average_rate": ["average rate", "average", "mid rate"],
}

KNOWN_CURRENCIES = {"USD", "KES", "UGX", "UGS", "BIF", "TZS", "ZAR", "EUR", "GBP"}


def parse_exchange_rates(tables, extraction_method="table_parser"):
    """Returns (records, rejected).

    Column order (buy vs. sell first) varies between report vintages — real official
    reports have been seen with "Currency Sell Buy Average" — so field order is
    discovered from the header text (`locate_header_block`) rather than assumed fixed.
    """
    records = []
    rejected = []

    for table in tables:
        header_end, field_order = locate_header_block(table.rows, COLUMN_ALIASES)
        if header_end is None or "currency" not in field_order:
            continue

        index_mapping = match_columns(table.header, COLUMN_ALIASES) if header_end == 1 else {}
        data_rows = table.rows[header_end:]

        for row in data_rows:
            if not any(c and str(c).strip() for c in row):
                continue

            clean = "currency" in index_mapping and not is_degenerate_row(row)
            if clean:
                raw = {f: cell(row, idx) for f, idx in index_mapping.items()}
            else:
                raw, reason = resolve_row_fields(row, field_order)
                if raw is None:
                    rejected.append({"page": table.page_number, "raw": " | ".join(str(c) for c in row),
                                      "reason": reason})
                    continue

            currency = raw.get("currency")
            if is_blank(currency):
                continue
            currency = currency.strip().upper()
            if currency == "UGS":
                currency = "UGX"

            fields = {
                "currency": currency,
                "buy_rate": parse_number(raw.get("buy_rate")),
                "sell_rate": parse_number(raw.get("sell_rate")),
                "average_rate": parse_number(raw.get("average_rate")),
            }
            if fields["average_rate"] is None and fields["buy_rate"] is not None and fields["sell_rate"] is not None:
                fields["average_rate"] = round((fields["buy_rate"] + fields["sell_rate"]) / 2, 4)

            record = ParsedRecord(fields, table.page_number, extraction_method,
                                   raw_text=" | ".join(str(c) for c in row))
            if currency not in KNOWN_CURRENCIES:
                record.mark_invalid("currency")
            records.append(record)

    return records, rejected
