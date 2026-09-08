from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from flask_wtf import FlaskForm
from wtforms import DateField, StringField, TextAreaField
from wtforms.validators import Length, Optional

from app.auth.decorators import roles_required
from app.extensions import db
from app.models.report import Report
from app.services.audit import log_action

reports_bp = Blueprint("reports", __name__)

STATUS_FILTERS = {
    "review_required": "Review Required",
    "validation_required": "Processed",
    "approved": "Verified",
    "failed": "Failed",
    "processing": "Processing",
    "uploaded": "Uploaded",
}


class ReportEditForm(FlaskForm):
    display_name = StringField("Report Name", validators=[Optional(), Length(max=255)])
    report_date = DateField("Report Date", validators=[Optional()])
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=4000)])


@reports_bp.route("/")
@login_required
def list_reports():
    query = Report.query

    search = (request.args.get("q") or "").strip()
    if search:
        like = f"%{search}%"
        conditions = [Report.original_filename.ilike(like), Report.display_name.ilike(like)]
        if search.isdigit():
            conditions.append(Report.id == int(search))
        query = query.filter(db.or_(*conditions))

    status = request.args.get("status")
    if status == "approved":
        query = query.filter(Report.approval_status == "approved")
    elif status in STATUS_FILTERS:
        query = query.filter(Report.processing_status == status)

    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    if date_from:
        query = query.filter(Report.report_date >= date_from)
    if date_to:
        query = query.filter(Report.report_date <= date_to)

    reports = query.order_by(Report.report_date.desc().nullslast(), Report.id.desc()).all()
    return render_template("reports/list.html", reports=reports, status_filters=STATUS_FILTERS,
                            search=search, status=status or "", date_from=date_from or "", date_to=date_to or "")


@reports_bp.route("/browse")
@login_required
def browse_reports():
    reports = (Report.query.filter_by(approval_status="approved")
               .order_by(
                   Report.report_date.desc().nullslast(), Report.id.desc()
               ).all())
    return render_template("reports/browse.html", reports=reports)


@reports_bp.route("/upload")
@login_required
def upload_page():
    return render_template("reports/upload.html")


def _get_report_or_404(report_id):
    report = db.session.get(Report, report_id)
    if report is None:
        abort(404)
    return report


@reports_bp.route("/<int:report_id>/preview")
@login_required
def preview_page(report_id):
    report = _get_report_or_404(report_id)
    return render_template("reports/preview.html", report=report)


@reports_bp.route("/<int:report_id>/review")
@login_required
def review_page(report_id):
    report = _get_report_or_404(report_id)
    return render_template("reports/review.html", report=report)


@reports_bp.route("/<int:report_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("administrator")
def edit_page(report_id):
    report = _get_report_or_404(report_id)
    form = ReportEditForm(obj=report if request.method == "GET" else None)
    if request.method == "GET":
        form.display_name.data = report.display_name
        form.report_date.data = report.report_date
        form.notes.data = report.notes

    if form.validate_on_submit():
        changes = []
        new_name = (form.display_name.data or "").strip() or None
        if new_name != report.display_name:
            changes.append(f"name -> {new_name or report.original_filename}")
            report.display_name = new_name
        if form.report_date.data != report.report_date:
            changes.append(f"report_date -> {form.report_date.data}")
            report.report_date = form.report_date.data
        if form.notes.data != report.notes:
            changes.append("notes updated")
            report.notes = form.notes.data

        if changes:
            db.session.commit()
            log_action("update_report_metadata", entity_type="report", entity_id=report.id,
                       description="; ".join(changes))
            flash("Report information updated successfully.", "success")
        else:
            flash("No changes to save.", "info")
        return redirect(url_for("reports.list_reports"))

    return render_template("reports/edit.html", report=report, form=form)
