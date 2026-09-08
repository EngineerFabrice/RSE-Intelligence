import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, current_app, request, send_file
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from app.api.utils import error, ok, to_dict
from app.auth.decorators import can_approve_required, can_edit_required, roles_required
from app.export.csv_export import DATASET_EXPORTERS
from app.export.excel_export import export_report_to_excel
from app.export.pdf_export import export_report_to_pdf
from app.extensions import db
from app.ingestion import pipeline
from app.ingestion.normalizers import parse_date
from app.models.extraction_record import ExtractionRecord
from app.models.report import Report
from app.models.validation_issue import Correction, ValidationIssue
from app.services import background_tasks, duplicate_detection
from app.services.audit import log_action
from app.services.progress import compute_progress

reports_api_bp = Blueprint("reports_api", __name__)


def _pdf_signature_ok(file_bytes: bytes) -> bool:
    return file_bytes[:5] == b"%PDF-"


def _report_payload(report):
    """Report fields plus a computed, presentation-only progress percentage/message
    (see app.services.progress) — used by the upload page's progress indicator so it
    never needs the internal step names."""
    payload = to_dict(report)
    payload["progress"] = compute_progress(report)
    label, key = report.status_label()
    payload["status_label"] = label
    payload["status_key"] = key
    return payload


@reports_api_bp.route("/upload", methods=["POST"])
@login_required
@can_edit_required
def upload_report():
    if "file" not in request.files:
        return error("No file was provided.", "missing_file")

    upload = request.files["file"]
    if not upload.filename:
        return error("No file was selected.", "missing_file")

    original_filename = secure_filename(upload.filename)
    if not original_filename.lower().endswith(".pdf"):
        return error("Only PDF files are accepted.", "invalid_file_type")

    file_bytes = upload.read()
    if not _pdf_signature_ok(file_bytes):
        return error("The uploaded file is not a valid PDF.", "invalid_file_type")

    file_hash = duplicate_detection.compute_file_hash(file_bytes)
    existing, reason = duplicate_detection.find_duplicate(file_hash)
    if existing and request.args.get("force") != "true":
        return error(
            f"This report may already exist (report #{existing.id}, {existing.report_date}).",
            "duplicate_report", http_status=409,
        )

    stored_name = f"{uuid.uuid4().hex}.pdf"
    storage_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
    with open(storage_path, "wb") as f:
        f.write(file_bytes)

    report = Report(
        filename=stored_name,
        original_filename=original_filename,
        file_hash=file_hash,
        storage_path=storage_path,
        file_size_bytes=len(file_bytes),
        upload_time=datetime.now(timezone.utc),
        processing_status="uploaded",
        uploaded_by_id=current_user.id,
    )
    db.session.add(report)
    db.session.commit()

    log_action("upload", entity_type="report", entity_id=report.id,
               description=f"Uploaded {original_filename}")

    background_tasks.submit(current_app._get_current_object(), pipeline.process_report, report.id)

    return ok(_report_payload(report), message="File uploaded. Processing has started.")


@reports_api_bp.route("/<int:report_id>/process", methods=["POST"])
@login_required
@can_edit_required
def reprocess_report(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)

    # Re-running extraction can change the dataset, so a previously verified report
    # must never keep showing as verified without a human re-checking it (spec §6/§15).
    was_approved = report.approval_status == "approved"
    if was_approved:
        report.approval_status = "pending"
        report.approved_by_id = None
        report.approved_at = None
        db.session.commit()

    background_tasks.submit(current_app._get_current_object(), pipeline.process_report, report.id)
    log_action(
        "reprocess", entity_type="report", entity_id=report.id,
        description="Re-ran extraction; previous verification was revoked pending re-approval."
        if was_approved else None,
    )
    return ok(message="Reprocessing started.", invalidated_approval=was_approved)


@reports_api_bp.route("/<int:report_id>", methods=["PATCH", "PUT"])
@login_required
@roles_required("administrator")
def update_report(report_id):
    """Update administrative metadata only (spec §5) — never the extracted financial
    values themselves, which stay reachable exclusively through the review/resolve
    workflow so every change keeps its validation/audit trail."""
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)

    payload = request.get_json(silent=True) or {}
    changes = []

    if "display_name" in payload:
        new_name = (payload.get("display_name") or "").strip() or None
        if new_name != report.display_name:
            changes.append(f"name -> {new_name or report.original_filename}")
            report.display_name = new_name

    if "report_date" in payload:
        raw_date = payload.get("report_date")
        if raw_date:
            parsed = parse_date(raw_date)
            if parsed is None:
                return error("report_date could not be understood.", "invalid_date")
            if parsed != report.report_date:
                changes.append(f"report_date -> {parsed.isoformat()}")
                report.report_date = parsed
        else:
            if report.report_date is not None:
                changes.append("report_date -> cleared")
            report.report_date = None

    if "notes" in payload:
        new_notes = payload.get("notes")
        if new_notes != report.notes:
            changes.append("notes updated")
            report.notes = new_notes

    if not changes:
        return ok(to_dict(report), message="No changes to save.")

    db.session.commit()
    log_action("update_report_metadata", entity_type="report", entity_id=report.id,
               description="; ".join(changes))
    return ok(to_dict(report), message="Report information updated successfully.")


@reports_api_bp.route("/<int:report_id>", methods=["DELETE"])
@login_required
@roles_required("administrator")
def delete_report(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)

    report_label = report.name
    storage_path = report.storage_path

    try:
        # No cascade relationship exists from Report to Correction (corrections are an
        # immutable audit trail keyed by report_id, not a live ORM relationship), so it
        # is cleaned up explicitly; every other child table cascades via the
        # relationships defined on Report (see app/models/report.py).
        Correction.query.filter_by(report_id=report.id).delete()
        db.session.delete(report)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to delete report_id=%s", report_id)
        return error("The report could not be deleted. No data was removed.", "delete_failed", 500)

    if storage_path and os.path.exists(storage_path):
        try:
            os.remove(storage_path)
        except OSError:
            current_app.logger.exception("Deleted report %s from the database but could not remove "
                                          "its stored PDF at %s", report_id, storage_path)

    # Logged after the row is gone: audit_logs has no foreign key to reports, so this
    # record of the deletion survives the report it describes, by design (spec §9).
    log_action("DELETE_REPORT", entity_type="report", entity_id=report_id,
               description=f"Permanently deleted report #{report_id} ({report_label}) and its "
                           f"extracted market data.")

    return ok(message="Report deleted successfully.")


@reports_api_bp.route("", methods=["GET"])
@login_required
def list_reports():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    query = Report.query.order_by(Report.report_date.desc().nullslast(), Report.id.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok({
        "items": [to_dict(r) for r in items],
        "page": page, "per_page": per_page, "total": total,
    })


@reports_api_bp.route("/<int:report_id>", methods=["GET"])
@login_required
def get_report(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)
    return ok(_report_payload(report))


@reports_api_bp.route("/<int:report_id>/preview", methods=["GET"])
@login_required
def preview_report(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)

    stats = to_dict(report.market_statistics) if report.market_statistics else None
    report_payload = to_dict(report)
    label, key = report.status_label()
    report_payload["status_label"] = label
    report_payload["status_key"] = key
    payload = {
        "report": report_payload,
        "stock": [to_dict(e) for e in report.equities],
        "market_stats": stats,
        "indices": [to_dict(i) for i in report.indices],
        "bonds": [to_dict(b) for b in report.bonds],
        "bond_trades": [to_dict(t) for t in report.bond_trades],
        "exchange_rates": [to_dict(f) for f in report.exchange_rates],
        "closing_bell": [to_dict(c) for c in report.closing_bell_entries],
        "issues": [to_dict(i) for i in report.validation_issues],
        "open_issue_count": report.open_issue_count(),
    }
    return ok(payload)


@reports_api_bp.route("/<int:report_id>/source", methods=["GET"])
@login_required
def record_source(report_id):
    """Field-level lineage for one extracted record (spec §4/§14): original PDF page,
    section, extraction method, raw source text, and validation status per field."""
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)

    target_table = request.args.get("table")
    target_id = request.args.get("id", type=int)
    if not target_table or target_id is None:
        return error("Both 'table' and 'id' are required.", "missing_params")

    records = (
        report.extraction_records
        .filter_by(target_table=target_table, target_id=target_id)
        .order_by(ExtractionRecord.field_name)
        .all()
    )
    return ok({
        "report_id": report.id,
        "original_filename": report.original_filename,
        "target_table": target_table,
        "target_id": target_id,
        "fields": [to_dict(r, exclude=("report_id",)) for r in records],
    })


@reports_api_bp.route("/<int:report_id>/issues/<int:issue_id>/resolve", methods=["POST"])
@login_required
@can_edit_required
def resolve_issue(report_id, issue_id):
    issue = db.session.get(ValidationIssue, issue_id)
    if not issue or issue.report_id != report_id:
        return error("Issue not found.", "not_found", 404)

    payload = request.get_json(silent=True) or {}
    resolution = payload.get("resolution")  # chosen_a, chosen_b, corrected, dismissed
    resolved_value = payload.get("resolved_value")
    reason = payload.get("reason")

    if resolution not in ("chosen_a", "chosen_b", "corrected", "dismissed"):
        return error("A valid resolution type is required.", "invalid_resolution")

    if resolution == "chosen_a":
        resolved_value = issue.extracted_value
    elif resolution == "chosen_b":
        resolved_value = issue.alternative_value

    if resolution in ("chosen_a", "chosen_b", "corrected") and issue.target_table and issue.target_id and issue.field:
        db.session.add(Correction(
            report_id=report_id, target_table=issue.target_table, target_id=issue.target_id,
            field=issue.field, original_value=issue.extracted_value, corrected_value=resolved_value,
            reason=reason or resolution, source_reference=issue.source_a_label,
            corrected_by_id=current_user.id,
        ))

    issue.resolution = resolution
    issue.resolved_value = resolved_value
    issue.resolved_by_id = current_user.id
    issue.resolved_at = datetime.now(timezone.utc)
    issue.resolution_reason = reason
    db.session.commit()

    log_action("resolve_issue", entity_type="validation_issue", entity_id=issue.id,
               description=f"Resolved as {resolution}")
    return ok(to_dict(issue))


@reports_api_bp.route("/<int:report_id>/approve", methods=["POST"])
@login_required
@can_approve_required
def approve_report(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)

    open_critical = report.validation_issues.filter_by(severity="critical", resolution=None).count()
    if open_critical:
        return error(
            f"{open_critical} critical issue(s) must be resolved before this report can be approved.",
            "unresolved_critical_issues", http_status=409,
        )

    report.approval_status = "approved"
    report.processing_status = "approved"
    report.approved_by_id = current_user.id
    report.approved_at = datetime.now(timezone.utc)
    db.session.commit()

    log_action("approve", entity_type="report", entity_id=report.id,
               description=f"Report approved by {current_user.email}")
    return ok(to_dict(report))


@reports_api_bp.route("/<int:report_id>/archive", methods=["POST"])
@login_required
@can_edit_required
def archive_report(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)
    report.processing_status = "archived"
    db.session.commit()
    log_action("archive", entity_type="report", entity_id=report.id)
    return ok(to_dict(report))


@reports_api_bp.route("/<int:report_id>/export/excel", methods=["GET"])
@login_required
def export_excel(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)
    buffer = export_report_to_excel(report)
    log_action("export", entity_type="report", entity_id=report.id, description="Exported Excel workbook")
    filename = f"RSE_Market_Report_{report.report_date or report.id}.xlsx"
    return send_file(buffer, as_attachment=True, download_name=filename,
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@reports_api_bp.route("/<int:report_id>/export/csv", methods=["GET"])
@login_required
def export_csv(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)
    dataset = request.args.get("dataset", "equities")
    exporter = DATASET_EXPORTERS.get(dataset)
    if not exporter:
        return error(f"Unknown dataset '{dataset}'.", "invalid_dataset")
    buffer = exporter(report)
    log_action("export", entity_type="report", entity_id=report.id, description=f"Exported CSV ({dataset})")
    filename = f"RSE_{dataset}_{report.report_date or report.id}.csv"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="text/csv")


@reports_api_bp.route("/<int:report_id>/export/pdf", methods=["GET"])
@login_required
def export_pdf(report_id):
    report = db.session.get(Report, report_id)
    if not report:
        return error("Report not found.", "not_found", 404)
    buffer = export_report_to_pdf(report)
    log_action("export", entity_type="report", entity_id=report.id, description="Exported PDF report")
    filename = f"RSE_Market_Report_{report.report_date or report.id}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")
