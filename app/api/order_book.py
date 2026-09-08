from flask import Blueprint, request
from flask_login import login_required

from app.api.utils import ok, to_dict
from app.models.report import Report

order_book_api_bp = Blueprint("order_book_api", __name__)


@order_book_api_bp.route("", methods=["GET"])
@login_required
def order_book():
    report_id = request.args.get("report_id", type=int)
    if report_id:
        report = Report.query.get(report_id)
    else:
        report = Report.query.filter_by(approval_status="approved").order_by(Report.report_date.desc()).first()

    if not report:
        return ok([])
    return ok([to_dict(c) for c in report.closing_bell_entries])
