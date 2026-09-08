import re

from app.ingestion.normalizers import parse_integer, parse_number
from app.ingestion.parsers.base import ParsedRecord

# Real official reports present these three figures as a small "Previous / Today /
# Points / %Change" mini-table (frequently collapsed by pdfplumber into one cell per
# row, e.g. "Shares traded               0.00     21,700     21,700   100.00"). The
# value we want is "Today" — the 2nd of the four numbers — not the first number
# encountered after the label, which is "Previous" and is typically 0.00.
_TRADING_STAT_LABELS = {
    "shares_traded": [r"shares\s+traded"],
    "equity_turnover": [r"equity\s+turnover"],
    "number_of_deals": [r"number\s+of\s+deals", r"no\.?\s+of\s+deals"],
}
_FOUR_NUMBER_RE = r"((?:\(?-?[\d,]+\.?\d*\)?\s+){3}\(?-?[\d,]+\.?\d*\)?)"
_INT_TRADING_STAT_FIELDS = {"shares_traded", "number_of_deals"}
# Fallback for reports that simply state "Shares Traded: 21,700" as a single label:value
# line rather than the Previous/Today/Points/%Change mini-table.
_SINGLE_VALUE_RE = r"[:\s]+\(?\-?[\d,]*\.?\d*%?\)?"

# Simple "label: value" fields that (per available evidence) appear as a single
# adjacent number, optionally after a parenthetical unit qualifier like "(Frw)".
_SIMPLE_LABEL_PATTERNS = {
    "bond_turnover": [r"bond\s+turnover"],
    "market_capitalization": [r"market\s+capitali[sz]ation"],
    "repo_value": [r"repo\s+value", r"repo\s+turnover"],
    "repo_deals": [r"repo\s+deals"],
    "repo_rate": [r"repo\s+rate"],
}
_SIMPLE_VALUE_RE = r"\s*(?:\([^)]{0,20}\))?[:\s]+\(?\-?[\d,]*\.?\d*%?\)?"
_INT_SIMPLE_FIELDS = {"repo_deals"}

# Market overview narrative, e.g.:
#   "...recorded a turnover of Frw 206,685,500 worth of bonds traded in 5 deals on the
#   fixed-income market and Frw 14,307,500 from 21,700 shares traded in 4 deals on the
#   equities market."
# Fully deterministic (regex capture groups only) — used as a cross-check / fallback
# source, never as the sole silent source for a value that disagrees with the table.
_OVERVIEW_RE = re.compile(
    r"turnover\s+of\s+Frw\s+([\d,]+(?:\.\d+)?)\s+worth\s+of\s+bonds\s+traded\s+in\s+(\d+)\s+deals"
    r".{0,400}?Frw\s+([\d,]+(?:\.\d+)?)\s+from\s+([\d,]+)\s+shares\s+traded\s+in\s+(\d+)\s+deals",
    re.IGNORECASE | re.DOTALL,
)


def _extract_trading_stat_today(text):
    """Try the Previous/Today/Points/%Change mini-table pattern first (real reports);
    fall back to a plain single-value "Label: N" line for reports that state these
    figures that way instead."""
    found = {}
    for field, patterns in _TRADING_STAT_LABELS.items():
        for pattern in patterns:
            match = re.search(pattern + r"\s+" + _FOUR_NUMBER_RE, text, re.IGNORECASE)
            if match:
                numbers = match.group(1).split()
                if len(numbers) == 4:
                    value = parse_integer(numbers[1]) if field in _INT_TRADING_STAT_FIELDS else parse_number(numbers[1])
                    if value is not None:
                        found[field] = (value, match.group(0).strip())
                        break

            single = re.search(pattern + _SINGLE_VALUE_RE, text, re.IGNORECASE)
            if single:
                raw_value = re.sub(pattern, "", single.group(0), count=1, flags=re.IGNORECASE).strip(" :\t")
                value = parse_integer(raw_value) if field in _INT_TRADING_STAT_FIELDS else parse_number(raw_value)
                if value is not None:
                    found[field] = (value, single.group(0).strip())
                    break
    return found


def _extract_simple_labels(text):
    found = {}
    for field, patterns in _SIMPLE_LABEL_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern + _SIMPLE_VALUE_RE, text, re.IGNORECASE)
            if match:
                raw_value = re.sub(pattern, "", match.group(0), count=1, flags=re.IGNORECASE)
                raw_value = re.sub(r"\([^)]{0,20}\)", "", raw_value).strip(" :\t")
                value = parse_integer(raw_value) if field in _INT_SIMPLE_FIELDS else parse_number(raw_value)
                if value is not None:
                    found[field] = (value, match.group(0).strip())
                break
    return found


def parse_market_overview_narrative(pages):
    """Independent narrative-based figures for cross-checking (spec §9). Returns a dict
    of field -> value, or {} if the narrative paragraph isn't present/recognizable."""
    for page in pages:
        match = _OVERVIEW_RE.search(page.text)
        if match:
            bond_turnover, bond_deals, equity_turnover, shares_traded, equity_deals = match.groups()
            return {
                "bond_turnover": parse_number(bond_turnover),
                "equity_turnover": parse_number(equity_turnover),
                "shares_traded": parse_integer(shares_traded),
                "number_of_deals": parse_integer(equity_deals),
                "_bond_deals": parse_integer(bond_deals),
                "_source_page": page.page_number,
            }
    return {}


def parse_market_statistics(pages, extraction_method="native_text"):
    """Returns a single ParsedRecord representing report-wide statistics, or None if
    nothing was found. Prefers the structured trading-stat table/labels; falls back to
    the market-overview narrative only for fields the table didn't provide."""
    fields = {name: None for name in list(_TRADING_STAT_LABELS) + list(_SIMPLE_LABEL_PATTERNS)}
    source_page = None
    matched_lines = []
    sources = {}  # field -> "table" | "narrative"

    for page in pages:
        stat_matches = _extract_trading_stat_today(page.text)
        for field, (value, raw) in stat_matches.items():
            if fields[field] is None:
                fields[field] = value
                sources[field] = "table"
                source_page = source_page or page.page_number
                matched_lines.append(raw)

        simple_matches = _extract_simple_labels(page.text)
        for field, (value, raw) in simple_matches.items():
            if fields[field] is None:
                fields[field] = value
                sources[field] = "table"
                source_page = source_page or page.page_number
                matched_lines.append(raw)

    narrative = parse_market_overview_narrative(pages)
    for field in ("shares_traded", "equity_turnover", "number_of_deals", "bond_turnover"):
        if fields.get(field) is None and narrative.get(field) is not None:
            fields[field] = narrative[field]
            sources[field] = "narrative"
            source_page = source_page or narrative.get("_source_page")

    if all(v is None for k, v in fields.items()):
        return None

    fields["repo_tenor"] = None
    record = ParsedRecord(fields, source_page or (pages[0].page_number if pages else None),
                           extraction_method, raw_text=" | ".join(matched_lines))
    record.narrative_cross_check = narrative  # attached for reconciliation, not persisted directly

    core_required = {"shares_traded", "equity_turnover", "number_of_deals", "market_capitalization"}
    for field in core_required:
        if fields.get(field) is None:
            record.mark_invalid(field)
        elif sources.get(field) == "narrative":
            record.mark_invalid(field)  # sourced from prose only -> review, not silently high-confidence
    return record
