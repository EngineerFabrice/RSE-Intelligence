"""Deterministic market insights (spec §27).

Every insight is computed directly from approved database values. Nothing here invents
numbers — each insight carries the concrete figures that produced it so it stays
explainable and auditable.
"""

from datetime import date, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models.bond import Bond
from app.models.equity import Equity
from app.models.report import Report


def _approved_reports_query():
    return Report.query.filter_by(approval_status="approved")


def latest_approved_report():
    return _approved_reports_query().order_by(Report.report_date.desc()).first()


def most_active_security(report: Report):
    top = report.equities.filter(Equity.volume.isnot(None)).order_by(Equity.volume.desc()).first()
    if not top:
        return None
    return {
        "type": "most_active",
        "title": "Most Actively Traded Security",
        "symbol": top.symbol,
        "volume": top.volume,
        "explanation": f"{top.symbol} recorded the highest trading volume of the session at "
                        f"{top.volume:,} shares.",
    }


def biggest_movers(report: Report, limit: int = 3):
    movers = (
        report.equities.filter(Equity.change_percent.isnot(None))
        .order_by(func.abs(Equity.change_percent).desc())
        .limit(limit)
        .all()
    )
    results = []
    for m in movers:
        direction = "gained" if (m.change_percent or 0) >= 0 else "declined"
        results.append({
            "type": "price_movement",
            "title": "Notable Price Movement",
            "symbol": m.symbol,
            "change_percent": float(m.change_percent) if m.change_percent is not None else None,
            "explanation": f"{m.symbol} {direction} {abs(float(m.change_percent)):.2f}% to close at "
                            f"{m.closing_price}.",
        })
    return results


def unusual_volume_alerts(report: Report, threshold_multiplier: float = 2.0, lookback_sessions: int = 10):
    """Flag equities whose volume today is materially above their recent historical average."""
    alerts = []
    for eq in report.equities.filter(Equity.volume.isnot(None)):
        history = (
            db.session.query(Equity.volume)
            .join(Report, Equity.report_id == Report.id)
            .filter(
                Equity.symbol == eq.symbol,
                Report.approval_status == "approved",
                Report.id != report.id,
                Equity.volume.isnot(None),
            )
            .order_by(Report.report_date.desc())
            .limit(lookback_sessions)
            .all()
        )
        volumes = [h[0] for h in history if h[0] is not None]
        if len(volumes) < 3:
            continue
        avg = sum(volumes) / len(volumes)
        if avg > 0 and eq.volume >= avg * threshold_multiplier:
            change_pct = ((eq.volume - avg) / avg) * 100
            alerts.append({
                "type": "unusual_volume",
                "title": "High Volume Alert",
                "symbol": eq.symbol,
                "current_volume": eq.volume,
                "historical_average": round(avg, 2),
                "change_percent": round(change_pct, 2),
                "explanation": f"{eq.symbol} recorded unusually high trading volume relative to its "
                                f"{len(volumes)}-session historical average. Current volume: {eq.volume:,}. "
                                f"Historical average: {avg:,.0f}. Change: {change_pct:+.1f}%.",
            })
    return alerts


def upcoming_bond_maturities(within_days: int = 90):
    cutoff = date.today() + timedelta(days=within_days)
    bonds = (
        Bond.query.join(Report, Bond.report_id == Report.id)
        .filter(
            Report.approval_status == "approved",
            Bond.maturity_date.isnot(None),
            Bond.maturity_date >= date.today(),
            Bond.maturity_date <= cutoff,
        )
        .order_by(Bond.maturity_date.asc())
        .all()
    )
    return [
        {
            "type": "bond_maturity",
            "title": "Upcoming Bond Maturity",
            "security": b.security,
            "isin": b.isin,
            "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
            "explanation": f"{b.security} matures on {b.maturity_date.isoformat()}.",
        }
        for b in bonds
    ]


def generate_insights_for_report(report: Report):
    insights = []
    top = most_active_security(report)
    if top:
        insights.append(top)
    insights.extend(biggest_movers(report))
    insights.extend(unusual_volume_alerts(report))
    insights.extend(upcoming_bond_maturities())
    return insights
