"""Controlled RSE market-data query layer for the "Ask RSE Market" assistant.

Every function here is a plain, deterministic read against the platform's own
canonical database — never a source of invented numbers. This is the *only*
way the AI assistant (app/services/ai_assistant.py) is allowed to touch market
data: it cannot query the database directly, it can only call these functions
as tools, and every function returns exactly what is stored (or an explicit
"not found"/"no data" result) — nothing is fabricated, and missing values stay
`None` rather than being coerced to 0.

Like the rest of the API layer (see app/api/equities.py, app/api/bonds.py,
etc.), "canonical" market data means data from an *approved* report — the
platform's explicit human sign-off that a report's figures are correct (spec
§31). Report/validation-status questions are the one exception, since they
must also be able to talk about a report that hasn't been approved yet.
"""

from app.extensions import db
from app.models.bond import Bond
from app.models.bond_trade import BondTrade
from app.models.equity import Equity
from app.models.exchange_rate import ExchangeRate
from app.models.index import MarketIndex
from app.models.report import Report


def _num(value):
    """Decimal/None -> float/None, for JSON-safe tool output. Never coerces
    a missing value to 0."""
    return float(value) if value is not None else None


def _report_ref(report):
    """The source-transparency block every tool result carries: which report
    the figures came from, its date, and whether it's verified."""
    if report is None:
        return None
    return {
        "report_id": report.id,
        "report_name": report.name,
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "verified": report.approval_status == "approved",
        "status": "Verified" if report.approval_status == "approved" else report.status_label()[0],
    }


def _latest_approved_report(before_report_id=None):
    query = Report.query.filter_by(approval_status="approved")
    if before_report_id:
        query = query.filter(Report.id != before_report_id)
    return query.order_by(Report.report_date.desc(), Report.id.desc()).first()


def _resolve_report(report_id=None):
    """A specific approved report if report_id is given, otherwise the latest
    approved one. Returns None if nothing matches (never falls back to an
    unapproved report for a "canonical data" lookup)."""
    if report_id:
        report = db.session.get(Report, report_id)
        if report is None or report.approval_status != "approved":
            return None
        return report
    return _latest_approved_report()


def get_latest_report_status():
    """Whether the most recently uploaded report is the same as the most
    recently verified one — the correct, honest answer to "is the latest
    report fully verified?" (a report can be uploaded/processed without yet
    being approved)."""
    most_recent = Report.query.order_by(Report.id.desc()).first()
    latest_verified = _latest_approved_report()

    if most_recent is None:
        return {"found": False, "message": "No RSE market reports have been uploaded yet."}

    label, _ = most_recent.status_label()
    return {
        "found": True,
        "most_recent_report": {
            "report_id": most_recent.id,
            "report_name": most_recent.name,
            "report_date": most_recent.report_date.isoformat() if most_recent.report_date else None,
            "status": label,
            "verified": most_recent.approval_status == "approved",
            "open_validation_issues": most_recent.open_issue_count(),
        },
        "latest_verified_report": _report_ref(latest_verified),
        "latest_is_verified": bool(latest_verified) and most_recent.id == latest_verified.id,
    }


def get_market_overview(report_id=None):
    """Market statistics + indices + exchange rates for one verified report."""
    report = _resolve_report(report_id)
    if report is None:
        return {"found": False, "message": "No verified RSE market report is available yet."}

    stats = report.market_statistics
    return {
        "found": True,
        "report": _report_ref(report),
        "market_statistics": None if stats is None else {
            "shares_traded": stats.shares_traded,
            "equity_turnover": _num(stats.equity_turnover),
            "bond_turnover": _num(stats.bond_turnover),
            "number_of_deals": stats.number_of_deals,
            "market_capitalization": _num(stats.market_capitalization),
        },
        "indices": [
            {
                "index_name": i.index_name,
                "current_value": _num(i.current_value),
                "previous_value": _num(i.previous_value),
                "change": _num(i.change),
                "percentage_change": _num(i.percentage_change),
            }
            for i in report.indices
        ],
        "exchange_rates": [
            {
                "currency": r.currency,
                "buy_rate": _num(r.buy_rate),
                "sell_rate": _num(r.sell_rate),
                "average_rate": _num(r.average_rate),
            }
            for r in report.exchange_rates
        ],
    }


def get_equity(symbol):
    """The most recent verified snapshot of one equity security."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"found": False, "message": "No equity symbol was given."}

    row = (
        Equity.query.join(Report, Equity.report_id == Report.id)
        .filter(Equity.symbol == symbol, Report.approval_status == "approved")
        .order_by(Report.report_date.desc())
        .first()
    )
    if row is None:
        return {"found": False, "symbol": symbol,
                "message": f"No verified data was found for the symbol '{symbol}'."}

    return {
        "found": True,
        "report": _report_ref(row.report),
        "equity": {
            "symbol": row.symbol,
            "security_name": row.security_name,
            "closing_price": _num(row.closing_price),
            "previous_close": _num(row.previous_close),
            "change": _num(row.change),
            "change_percent": _num(row.change_percent),
            "today_high": _num(row.today_high),
            "today_low": _num(row.today_low),
            "high_12m": _num(row.high_12m),
            "low_12m": _num(row.low_12m),
            "volume": row.volume,
            "value_turnover": _num(row.value_turnover),
        },
    }


def get_equity_history(symbol, limit=10):
    """Verified closing prices for one symbol across past reports, oldest to
    newest, each tagged with its own report date."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"found": False, "message": "No equity symbol was given."}
    limit = max(1, min(int(limit or 10), 50))

    rows = (
        Equity.query.join(Report, Equity.report_id == Report.id)
        .filter(Equity.symbol == symbol, Report.approval_status == "approved")
        .order_by(Report.report_date.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return {"found": False, "symbol": symbol,
                "message": f"No verified historical data was found for the symbol '{symbol}'."}

    history = [
        {
            "report_date": r.report.report_date.isoformat() if r.report.report_date else None,
            "closing_price": _num(r.closing_price),
            "change_percent": _num(r.change_percent),
            "volume": r.volume,
        }
        for r in reversed(rows)
    ]
    return {"found": True, "symbol": symbol, "history": history}


def compare_equities(symbols):
    """Latest verified snapshots for several symbols, side by side, plus a
    backend-computed price/volume difference between the first two found
    (the model must never compute this itself)."""
    symbols = [s.strip().upper() for s in (symbols or []) if s and s.strip()]
    if len(symbols) < 2:
        return {"found": False, "message": "At least two equity symbols are needed to compare."}

    results = {s: get_equity(s) for s in symbols}
    found = {s: r for s, r in results.items() if r["found"]}
    missing = [s for s in symbols if s not in found]

    comparison = None
    if len(found) >= 2:
        (sym_a, res_a), (sym_b, res_b) = list(found.items())[:2]
        price_a, price_b = res_a["equity"]["closing_price"], res_b["equity"]["closing_price"]
        vol_a, vol_b = res_a["equity"]["volume"], res_b["equity"]["volume"]
        comparison = {
            "symbols": [sym_a, sym_b],
            "closing_price_difference": (
                round(price_a - price_b, 4) if price_a is not None and price_b is not None else None
            ),
            "volume_difference": (vol_a - vol_b) if vol_a is not None and vol_b is not None else None,
        }

    return {
        "found": bool(found),
        "equities": {s: r for s, r in found.items()},
        "missing_symbols": missing,
        "comparison": comparison,
    }


def top_performers(metric="volume", limit=5, report_id=None):
    """Rank equities from one verified report by a real, stored metric —
    never a value the model invents."""
    metric_columns = {
        "volume": Equity.volume,
        "change_percent": Equity.change_percent,
        "value_turnover": Equity.value_turnover,
    }
    column = metric_columns.get(metric, Equity.volume)
    limit = max(1, min(int(limit or 5), 20))

    report = _resolve_report(report_id)
    if report is None:
        return {"found": False, "message": "No verified RSE market report is available yet."}

    rows = (
        Equity.query.filter(Equity.report_id == report.id, column.isnot(None))
        .order_by(db.desc(db.func.abs(column)) if metric == "change_percent" else column.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return {"found": False, "report": _report_ref(report),
                "message": f"No equities in this report have a recorded {metric.replace('_', ' ')}."}

    return {
        "found": True,
        "report": _report_ref(report),
        "metric": metric,
        "ranking": [
            {
                "symbol": r.symbol,
                "security_name": r.security_name,
                "volume": r.volume,
                "change_percent": _num(r.change_percent),
                "value_turnover": _num(r.value_turnover),
                "closing_price": _num(r.closing_price),
            }
            for r in rows
        ],
    }


def get_indices(report_id=None):
    report = _resolve_report(report_id)
    if report is None:
        return {"found": False, "message": "No verified RSE market report is available yet."}

    rows = list(report.indices)
    if not rows:
        return {"found": False, "report": _report_ref(report),
                "message": "No index data was recorded in this verified report."}

    return {
        "found": True,
        "report": _report_ref(report),
        "indices": [
            {
                "index_name": i.index_name,
                "current_value": _num(i.current_value),
                "previous_value": _num(i.previous_value),
                "change": _num(i.change),
                "percentage_change": _num(i.percentage_change),
            }
            for i in rows
        ],
    }


def get_bonds(bond_type=None, report_id=None):
    report = _resolve_report(report_id)
    if report is None:
        return {"found": False, "message": "No verified RSE market report is available yet."}

    query = Bond.query.filter(Bond.report_id == report.id)
    if bond_type:
        query = query.filter(Bond.bond_type == bond_type)
    rows = query.order_by(Bond.maturity_date.asc().nullslast()).all()

    if not rows:
        return {"found": False, "report": _report_ref(report),
                "message": "No bond data was recorded in this verified report."}

    return {
        "found": True,
        "report": _report_ref(report),
        "bonds": [
            {
                "isin": b.isin,
                "security": b.security,
                "bond_type": b.bond_type,
                "status": b.status,
                "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
                "tenor": b.tenor,
                "coupon": _num(b.coupon),
                "close_price": _num(b.close_price),
                "traded_volume": _num(b.traded_volume),
                "bond_traded": b.bond_traded,
            }
            for b in rows
        ],
    }


def get_bond_trades(report_id=None, limit=20):
    report = _resolve_report(report_id)
    if report is None:
        return {"found": False, "message": "No verified RSE market report is available yet."}
    limit = max(1, min(int(limit or 20), 100))

    rows = (
        BondTrade.query.filter(BondTrade.report_id == report.id)
        .order_by(BondTrade.trade_date.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return {"found": False, "report": _report_ref(report),
                "message": "No bond trades were recorded in this verified report."}

    return {
        "found": True,
        "report": _report_ref(report),
        "bond_trades": [
            {
                "trade_date": t.trade_date.isoformat() if t.trade_date else None,
                "isin": t.isin,
                "security": t.security,
                "price_yield": _num(t.price_yield),
                "volume": t.volume,
                "value": _num(t.value),
                "number_of_trades": t.number_of_trades,
            }
            for t in rows
        ],
    }


def get_exchange_rates(currency=None, report_id=None):
    report = _resolve_report(report_id)
    if report is None:
        return {"found": False, "message": "No verified RSE market report is available yet."}

    rows = list(report.exchange_rates)
    if currency:
        currency = currency.strip().upper()
        rows = [r for r in rows if r.currency == currency]

    if not rows:
        msg = (f"No verified exchange rate for '{currency}' was found in this report."
               if currency else "No exchange rate data was recorded in this verified report.")
        return {"found": False, "report": _report_ref(report), "message": msg}

    return {
        "found": True,
        "report": _report_ref(report),
        "exchange_rates": [
            {
                "currency": r.currency,
                "buy_rate": _num(r.buy_rate),
                "sell_rate": _num(r.sell_rate),
                "average_rate": _num(r.average_rate),
            }
            for r in rows
        ],
    }


def get_exchange_rate_history(currency, limit=10):
    currency = (currency or "").strip().upper()
    if not currency:
        return {"found": False, "message": "No currency was given."}
    limit = max(1, min(int(limit or 10), 50))

    rows = (
        ExchangeRate.query.join(Report, ExchangeRate.report_id == Report.id)
        .filter(ExchangeRate.currency == currency, Report.approval_status == "approved")
        .order_by(Report.report_date.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return {"found": False, "currency": currency,
                "message": f"No verified historical rate data was found for '{currency}'."}

    history = [
        {
            "report_date": r.report.report_date.isoformat() if r.report.report_date else None,
            "buy_rate": _num(r.buy_rate),
            "sell_rate": _num(r.sell_rate),
            "average_rate": _num(r.average_rate),
        }
        for r in reversed(rows)
    ]
    return {"found": True, "currency": currency, "history": history}


# Dispatch table used by app/services/ai_assistant.py to execute a tool call
# the model requested. Keeping this here (next to the functions themselves)
# keeps the two in sync by construction.
TOOL_FUNCTIONS = {
    "get_latest_report_status": get_latest_report_status,
    "get_market_overview": get_market_overview,
    "get_equity": get_equity,
    "get_equity_history": get_equity_history,
    "compare_equities": compare_equities,
    "top_performers": top_performers,
    "get_indices": get_indices,
    "get_bonds": get_bonds,
    "get_bond_trades": get_bond_trades,
    "get_exchange_rates": get_exchange_rates,
    "get_exchange_rate_history": get_exchange_rate_history,
}
