from flask import Blueprint, request
from flask_login import login_required

from app.api.utils import ok
from app.models.report import Report
from app.services.insights import generate_insights_for_report

insights_api_bp = Blueprint("insights_api", __name__)


@insights_api_bp.route("", methods=["GET"])
@login_required
def insights():
    report_id = request.args.get("report_id", type=int)
    if report_id:
        report = Report.query.get(report_id)
    else:
        report = Report.query.filter_by(approval_status="approved").order_by(Report.report_date.desc()).first()

    if not report:
        return ok([])
    return ok(generate_insights_for_report(report))
