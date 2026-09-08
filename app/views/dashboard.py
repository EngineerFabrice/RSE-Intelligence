from flask import Blueprint, render_template
from flask_login import login_required

from app.models.report import Report

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    latest_report = Report.query.order_by(Report.id.desc()).first()
    return render_template("dashboard.html", latest_report=latest_report)
