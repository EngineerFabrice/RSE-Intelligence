from flask import Blueprint, request
from flask_login import login_required

from app.api.utils import ok, to_dict
from app.models.index import MarketIndex
from app.models.report import Report

indices_api_bp = Blueprint("indices_api", __name__)


@indices_api_bp.route("", methods=["GET"])
@login_required
def list_indices():
    latest_report = Report.query.filter_by(approval_status="approved").order_by(Report.report_date.desc()).first()
    if not latest_report:
        return ok([])
    return ok([to_dict(i) for i in latest_report.indices])


@indices_api_bp.route("/<string:index_name>/history", methods=["GET"])
@login_required
def index_history(index_name):
    rows = (
        MarketIndex.query.join(Report, MarketIndex.report_id == Report.id)
        .filter(MarketIndex.index_name == index_name.upper(), Report.approval_status == "approved")
        .order_by(Report.report_date.asc())
        .all()
    )
    history = [
        {"report_date": r.report.report_date.isoformat() if r.report.report_date else None,
         "current_value": float(r.current_value) if r.current_value is not None else None}
        for r in rows
    ]
    return ok({"index_name": index_name.upper(), "history": history})
