from flask import Blueprint
from flask_login import login_required

from app.api.utils import ok, to_dict
from app.models.exchange_rate import ExchangeRate
from app.models.report import Report

exchange_rates_api_bp = Blueprint("exchange_rates_api", __name__)


@exchange_rates_api_bp.route("", methods=["GET"])
@login_required
def list_exchange_rates():
    latest_report = Report.query.filter_by(approval_status="approved").order_by(Report.report_date.desc()).first()
    if not latest_report:
        return ok([])
    return ok([to_dict(f) for f in latest_report.exchange_rates])


@exchange_rates_api_bp.route("/<string:currency>/history", methods=["GET"])
@login_required
def rate_history(currency):
    rows = (
        ExchangeRate.query.join(Report, ExchangeRate.report_id == Report.id)
        .filter(ExchangeRate.currency == currency.upper(), Report.approval_status == "approved")
        .order_by(Report.report_date.asc())
        .all()
    )
    history = [
        {"report_date": r.report.report_date.isoformat() if r.report.report_date else None,
         "buy_rate": float(r.buy_rate) if r.buy_rate is not None else None,
         "sell_rate": float(r.sell_rate) if r.sell_rate is not None else None,
         "average_rate": float(r.average_rate) if r.average_rate is not None else None}
        for r in rows
    ]
    return ok({"currency": currency.upper(), "history": history})
