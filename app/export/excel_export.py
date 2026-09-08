"""Professional analyst-ready Excel export (spec §3, §4, §49).

Builds a real, formatted .xlsx workbook with five sheets: STOCK, MARKET STATS, BONDS,
BONDS TRADES, EXCHANGE RATE. The sheet/column layout matches the organization's
reference workbook (clean single header row per sheet, navy #1F4E78 header styling,
no metadata preamble) rather than a generic dump of every stored field — each sheet
shows exactly the figures an analyst reads day to day.
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models.bond import Bond
from app.models.equity import Equity
from app.models.exchange_rate import ExchangeRate

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=10)

NUMBER_FORMATS = {
    "int": "#,##0",
    "number": "#,##0.00",
    "text": "General",
    "date": "dd-mmm-yyyy",
}


def _num(v):
    return float(v) if v is not None else None


def _category_label(bond_type):
    return {"government": "TREASURY", "corporate": "CORPORATE"}.get((bond_type or "").lower(), "TREASURY")


def _write_table(ws, columns, rows, col_widths=None):
    """Writes a single header row (navy fill, bold white text) starting at A1, followed
    by data rows — matching the reference workbook exactly (no metadata preamble, no
    frozen panes, no autofilter)."""
    for col_idx, (label, _getter, _fmt) in enumerate(columns, start=1):
        c = ws.cell(row=1, column=col_idx, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center")

    for r_offset, row_obj in enumerate(rows, start=1):
        for col_idx, (_label, getter, fmt) in enumerate(columns, start=1):
            c = ws.cell(row=1 + r_offset, column=col_idx, value=getter(row_obj))
            c.number_format = NUMBER_FORMATS.get(fmt, "General")

    for col_idx, (label, _getter, _fmt) in enumerate(columns, start=1):
        letter = get_column_letter(col_idx)
        width = (col_widths or {}).get(col_idx, max(11, len(label) + 2))
        ws.column_dimensions[letter].width = width


def _build_stock_sheet(ws, report):
    columns = [
        ("SECURITY", lambda e: e.symbol, "text"),
        ("CLOSING", lambda e: _num(e.closing_price), "int"),
        ("VOLUME", lambda e: e.volume, "int"),
        ("VALUE", lambda e: _num(e.value_turnover), "int"),
    ]
    rows = list(report.equities.order_by(Equity.symbol))
    _write_table(ws, columns, rows, col_widths={1: 11, 2: 10, 3: 11, 4: 13})


def _build_market_stats_sheet(ws, report):
    columns = [
        ("INDICATORS", lambda kv: kv[0], "text"),
        ("CLOSING", lambda kv: kv[1], "number"),
    ]
    rows = [(idx.index_name, _num(idx.current_value)) for idx in report.indices]

    stats = report.market_statistics
    if stats:
        if stats.equity_turnover is not None:
            rows.append(("Equity turnover", _num(stats.equity_turnover)))
        if stats.bond_turnover is not None:
            rows.append(("Bond market today (FRW)", _num(stats.bond_turnover)))
        if stats.market_capitalization is not None:
            rows.append(("Market capitalization (FRW)", _num(stats.market_capitalization)))

    _write_table(ws, columns, rows, col_widths={1: 30, 2: 18})


def _build_bonds_sheet(ws, report):
    columns = [
        ("T-BONDS No", lambda item: item[0], "int"),
        ("ISIN-CODE", lambda item: item[1].isin, "text"),
        # Not present in the daily trading report this platform ingests — left blank
        # rather than fabricated. Populated automatically if a future source provides it.
        ("ISSUE DATE", lambda item: None, "date"),
        ("MATURITY DATE", lambda item: item[1].maturity_date, "date"),
        ("COUPON RATE", lambda item: _num(item[1].coupon), "number"),
        ("YIELD TM", lambda item: None, "number"),
        ("BOND CATEGORY", lambda item: _category_label(item[1].bond_type), "text"),
        ("CLOSING PRICE", lambda item: _num(item[1].close_price), "number"),
    ]
    bonds = list(report.bonds.order_by(Bond.maturity_date))
    rows = list(enumerate(bonds, start=1))
    _write_table(ws, columns, rows, col_widths={1: 13, 2: 12, 3: 13, 4: 16, 5: 14, 6: 11, 7: 16, 8: 15})


def _build_bond_trades_sheet(ws, report):
    columns = [
        ("BOND", lambda b: f"{b.security} ({b.status})" if b.status else b.security, "text"),
        ("CATEGORY", lambda b: _category_label(b.bond_type), "text"),
        ("VOLUME", lambda b: _num(b.traded_volume), "int"),
        ("PREVIOUS", lambda b: _num(b.previous_value), "number"),
        ("CLOSING", lambda b: _num(b.close_price), "number"),
        ("CHANGE", lambda b: (
            round(float(b.close_price) - float(b.previous_value), 4)
            if b.close_price is not None and b.previous_value is not None else None
        ), "number"),
    ]
    # Only bonds actually traded that session belong here — the full listing (traded or
    # not) is the BONDS sheet.
    rows = [b for b in report.bonds if b.bond_traded and b.traded_volume]
    _write_table(ws, columns, rows, col_widths={1: 30, 2: 11, 3: 13, 4: 11, 5: 10, 6: 9})


def _build_exchange_rate_sheet(ws, report):
    columns = [
        ("CURRENCY CODE", lambda f: f.currency, "text"),
        ("BUYING VALUE", lambda f: _num(f.buy_rate), "number"),
        ("SELLING VALUE", lambda f: _num(f.sell_rate), "number"),
    ]
    rows = list(report.exchange_rates.order_by(ExchangeRate.currency))
    _write_table(ws, columns, rows, col_widths={1: 16, 2: 15, 3: 16})


def build_workbook(report):
    wb = Workbook()
    wb.remove(wb.active)

    sheet_builders = [
        ("STOCK", _build_stock_sheet),
        ("MARKET STATS", _build_market_stats_sheet),
        ("BONDS", _build_bonds_sheet),
        ("BONDS TRADES", _build_bond_trades_sheet),
        ("EXCHANGE RATE", _build_exchange_rate_sheet),
    ]
    for title, builder in sheet_builders:
        ws = wb.create_sheet(title=title)
        builder(ws, report)

    wb.properties.title = f"RSE Market Report {report.report_date or ''}".strip()
    wb.properties.creator = "RSE Intelligence Platform"
    wb.properties.subject = "Rwanda Stock Exchange Market Report"

    return wb


def export_report_to_excel(report) -> io.BytesIO:
    wb = build_workbook(report)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
