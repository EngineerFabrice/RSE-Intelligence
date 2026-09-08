from flask import Blueprint, request
from flask_login import login_required

from app.api.utils import ok, to_dict
from app.models.market_statistics import MarketStatistics
from app.models.report import Report
from app.services.market_narrative import generate_narrative

market_api_bp = Blueprint("market_api", __name__)


@market_api_bp.route("/overview", methods=["GET"])
@login_required
def market_overview():
    latest_report = Report.query.filter_by(approval_status="approved").order_by(Report.report_date.desc()).first()
    if not latest_report:
        return ok({"report": None, "message": "No approved market data is available yet."})

    return ok({
        "report": to_dict(latest_report),
        "market_statistics": to_dict(latest_report.market_statistics) if latest_report.market_statistics else None,
        "indices": [to_dict(i) for i in latest_report.indices],
        "exchange_rates": [to_dict(f) for f in latest_report.exchange_rates],
        "narrative": generate_narrative(latest_report),
    })


@market_api_bp.route("/history", methods=["GET"])
@login_required
def market_history():
    start = request.args.get("start")
    end = request.args.get("end")

    query = (
        MarketStatistics.query.join(Report, MarketStatistics.report_id == Report.id)
        .filter(Report.approval_status == "approved")
    )
    if start:
        query = query.filter(Report.report_date >= start)
    if end:
        query = query.filter(Report.report_date <= end)
    query = query.order_by(Report.report_date.asc())

    history = []
    for stats in query.all():
        history.append({
            "report_date": stats.report.report_date.isoformat() if stats.report.report_date else None,
            "equity_turnover": float(stats.equity_turnover) if stats.equity_turnover is not None else None,
            "bond_turnover": float(stats.bond_turnover) if stats.bond_turnover is not None else None,
            "shares_traded": stats.shares_traded,
            "number_of_deals": stats.number_of_deals,
            "market_capitalization": float(stats.market_capitalization) if stats.market_capitalization is not None else None,
        })
    return ok(history)


@market_api_bp.route("/data-quality", methods=["GET"])
@login_required
def data_quality():
    total = Report.query.count()
    approved = Report.query.filter_by(approval_status="approved").count()
    needs_review = Report.query.filter_by(processing_status="review_required").count()
    failed = Report.query.filter_by(processing_status="failed").count()

    confidences = [
        r.overall_confidence for r in Report.query.filter(Report.overall_confidence.isnot(None)).all()
    ]
    avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None

    return ok({
        "reports_processed": total,
        "approved": approved,
        "needs_review": needs_review,
        "failed": failed,
        "average_confidence": avg_confidence,
    })
