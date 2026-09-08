"""CSV export (spec §48). Reuses the same query layer as the Excel export."""

import csv
import io


def _rows_to_csv(columns, rows) -> io.BytesIO:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([label for label, _getter in columns])
    for row_obj in rows:
        writer.writerow([_stringify(getter(row_obj)) for _label, getter in columns])
    encoded = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    encoded.seek(0)
    return encoded


def _stringify(value):
    if value is None:
        return ""
    return str(value)


def export_equities_csv(report):
    columns = [
        ("ISIN", lambda e: e.isin), ("Symbol", lambda e: e.symbol), ("Security Name", lambda e: e.security_name),
        ("12M High", lambda e: e.high_12m), ("12M Low", lambda e: e.low_12m),
        ("Today High", lambda e: e.today_high), ("Today Low", lambda e: e.today_low),
        ("Closing Price", lambda e: e.closing_price), ("Previous Close", lambda e: e.previous_close),
        ("Change", lambda e: e.change), ("Change %", lambda e: e.change_percent),
        ("Volume", lambda e: e.volume), ("Value/Turnover", lambda e: e.value_turnover),
    ]
    return _rows_to_csv(columns, list(report.equities))


def export_bonds_csv(report):
    columns = [
        ("ISIN", lambda b: b.isin), ("Status", lambda b: b.status), ("Security", lambda b: b.security),
        ("Maturity Date", lambda b: b.maturity_date), ("Tenor", lambda b: b.tenor),
        ("Coupon", lambda b: b.coupon), ("Close Price", lambda b: b.close_price),
        ("Previous Value", lambda b: b.previous_value), ("Bids", lambda b: b.bids), ("Offers", lambda b: b.offers),
    ]
    return _rows_to_csv(columns, list(report.bonds))


def export_bond_trades_csv(report):
    columns = [
        ("Trade Date", lambda t: t.trade_date), ("ISIN", lambda t: t.isin), ("Security", lambda t: t.security),
        ("Price/Yield", lambda t: t.price_yield), ("Volume", lambda t: t.volume), ("Value", lambda t: t.value),
        ("Number of Trades", lambda t: t.number_of_trades),
    ]
    return _rows_to_csv(columns, list(report.bond_trades))


def export_exchange_rates_csv(report):
    columns = [
        ("Currency", lambda f: f.currency), ("Buy Rate", lambda f: f.buy_rate),
        ("Sell Rate", lambda f: f.sell_rate), ("Average Rate", lambda f: f.average_rate),
    ]
    return _rows_to_csv(columns, list(report.exchange_rates))


def export_market_statistics_csv(report):
    stats = report.market_statistics
    columns = [("Metric", lambda kv: kv[0]), ("Value", lambda kv: kv[1])]
    rows = []
    if stats:
        rows = [
            ("Shares Traded", stats.shares_traded), ("Equity Turnover", stats.equity_turnover),
            ("Bond Turnover", stats.bond_turnover), ("Number of Deals", stats.number_of_deals),
            ("Market Capitalization", stats.market_capitalization), ("Repo Value", stats.repo_value),
            ("Repo Deals", stats.repo_deals), ("Repo Rate", stats.repo_rate),
        ]
    return _rows_to_csv(columns, rows)


DATASET_EXPORTERS = {
    "equities": export_equities_csv,
    "bonds": export_bonds_csv,
    "bond_trades": export_bond_trades_csv,
    "exchange_rates": export_exchange_rates_csv,
    "market_statistics": export_market_statistics_csv,
}
