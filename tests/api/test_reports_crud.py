"""Admin Dashboard Report Management CRUD: create/read already covered by
test_reports_workflow.py and test_auth_and_rbac.py — this file covers Update, Delete,
their cascade/audit behavior, and the authorization matrix."""

import os

from tests.fixtures.sample_report import build_sample_pdf

from app.extensions import db
from app.ingestion.pipeline import process_report
from app.models.audit_log import AuditLog
from app.models.bond import Bond
from app.models.closing_bell import ClosingBellEntry
from app.models.equity import Equity
from app.models.exchange_rate import ExchangeRate
from app.models.extraction_diagnostic import ExtractionDiagnostic
from app.models.extraction_record import ExtractionRecord
from app.models.index import MarketIndex
from app.models.market_statistics import MarketStatistics
from app.models.report import Report
from app.models.validation_issue import Correction, ValidationIssue
from app.services import duplicate_detection


def _seed_processed_report(app, tmp_path, mismatch=False, name="sample.pdf"):
    pdf_path = tmp_path / name
    build_sample_pdf(pdf_path, shares_traded_mismatch=mismatch)
    file_bytes = pdf_path.read_bytes()

    report = Report(filename=name, original_filename=name,
                     file_hash=duplicate_detection.compute_file_hash(file_bytes), storage_path=str(pdf_path))
    db.session.add(report)
    db.session.commit()
    process_report(report.id)
    db.session.refresh(report)
    return report


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def test_admin_can_update_report_metadata(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path)
    resp = admin_client.patch(f"/api/reports/{report.id}", json={
        "display_name": "September Market Report", "notes": "Flagged for spot-check.",
    })
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["display_name"] == "September Market Report"
    assert body["notes"] == "Flagged for spot-check."


def test_update_creates_audit_log_entry(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path)
    admin_client.patch(f"/api/reports/{report.id}", json={"display_name": "Renamed"})
    entry = AuditLog.query.filter_by(action="update_report_metadata", entity_id=report.id).first()
    assert entry is not None
    assert "Renamed" in entry.description


def test_update_rejects_unparseable_date(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path)
    resp = admin_client.patch(f"/api/reports/{report.id}", json={"report_date": "not a date"})
    assert resp.status_code == 400


def test_update_never_touches_extracted_financial_values(admin_client, app, tmp_path):
    # The update endpoint only recognizes display_name/report_date/notes — extra keys
    # are silently ignored, never applied to extracted data.
    report = _seed_processed_report(app, tmp_path)
    equity_before = report.equities.first().closing_price
    admin_client.patch(f"/api/reports/{report.id}", json={
        "display_name": "x", "equities": [{"symbol": "HACKED", "closing_price": 999999}],
    })
    db.session.refresh(report)
    assert report.equities.first().closing_price == equity_before
    assert report.equities.first().symbol != "HACKED"


def test_analyst_reviewer_viewer_cannot_update(analyst_client, reviewer_client, viewer_client, app, tmp_path):
    for client in (analyst_client, reviewer_client, viewer_client):
        report = _seed_processed_report(app, tmp_path, name=f"u_{id(client)}.pdf")
        resp = client.patch(f"/api/reports/{report.id}", json={"display_name": "nope"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Delete — cascade and data isolation
# ---------------------------------------------------------------------------

def test_admin_can_delete_report(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path)
    report_id = report.id
    resp = admin_client.delete(f"/api/reports/{report_id}")
    assert resp.status_code == 200
    assert db.session.get(Report, report_id) is None


def test_delete_cascades_all_report_specific_children(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path, mismatch=True)  # mismatch -> has issues/corrections too
    report_id = report.id

    # Resolve an issue first so a Correction row exists (Correction has no ORM cascade
    # relationship — the delete endpoint must clean it up explicitly).
    issue = report.validation_issues.filter_by(resolution=None).first()
    if issue and issue.target_table and issue.target_id and issue.field:
        admin_client.post(f"/api/reports/{report_id}/issues/{issue.id}/resolve", json={"resolution": "chosen_a"})

    assert report.equities.count() > 0
    assert report.extraction_records.count() > 0
    assert ExtractionDiagnostic.query.filter_by(report_id=report_id).count() > 0

    resp = admin_client.delete(f"/api/reports/{report_id}")
    assert resp.status_code == 200

    assert Equity.query.filter_by(report_id=report_id).count() == 0
    assert Bond.query.filter_by(report_id=report_id).count() == 0
    assert MarketIndex.query.filter_by(report_id=report_id).count() == 0
    assert ExchangeRate.query.filter_by(report_id=report_id).count() == 0
    assert ClosingBellEntry.query.filter_by(report_id=report_id).count() == 0
    assert MarketStatistics.query.filter_by(report_id=report_id).count() == 0
    assert ExtractionRecord.query.filter_by(report_id=report_id).count() == 0
    assert ValidationIssue.query.filter_by(report_id=report_id).count() == 0
    assert ExtractionDiagnostic.query.filter_by(report_id=report_id).count() == 0
    assert Correction.query.filter_by(report_id=report_id).count() == 0


def test_delete_does_not_touch_other_reports(admin_client, app, tmp_path):
    keep = _seed_processed_report(app, tmp_path, name="keep.pdf")
    doomed = _seed_processed_report(app, tmp_path, name="doomed.pdf")
    keep_equity_count = keep.equities.count()

    admin_client.delete(f"/api/reports/{doomed.id}")

    assert db.session.get(Report, keep.id) is not None
    db.session.refresh(keep)
    assert keep.equities.count() == keep_equity_count


def test_delete_removes_the_stored_pdf_file(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path)
    path = report.storage_path
    assert os.path.exists(path)
    admin_client.delete(f"/api/reports/{report.id}")
    assert not os.path.exists(path)


def test_delete_records_audit_entry_that_survives_the_report(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path, name="to-delete.pdf")
    report_id = report.id
    admin_client.delete(f"/api/reports/{report_id}")

    entry = AuditLog.query.filter_by(action="DELETE_REPORT", entity_id=report_id).first()
    assert entry is not None
    assert "to-delete.pdf" in entry.description
    assert db.session.get(Report, report_id) is None  # the report is gone, the log is not


def test_delete_requires_confirmation_is_a_ui_concern_backend_still_deletes_on_call(admin_client, app, tmp_path):
    # The backend correctly has no notion of "confirmation" — that's enforced by the
    # modal in reports/list.html not calling the endpoint until the admin confirms.
    # This test just documents that the API itself deletes immediately when called,
    # which is why the UI-side confirmation step matters.
    report = _seed_processed_report(app, tmp_path)
    resp = admin_client.delete(f"/api/reports/{report.id}")
    assert resp.status_code == 200


def test_database_delete_ui_uses_confirmation_and_inline_success(admin_client):
    page = admin_client.get("/reports/").get_data(as_text=True)
    assert "Delete Report?" in page
    assert "Report deleted successfully." in page
    assert "data-report-row" in page
    assert "window.location.reload()" not in page


def test_analyst_reviewer_viewer_cannot_delete(analyst_client, reviewer_client, viewer_client, app, tmp_path):
    for client in (analyst_client, reviewer_client, viewer_client):
        report = _seed_processed_report(app, tmp_path, name=f"d_{id(client)}.pdf")
        resp = client.delete(f"/api/reports/{report.id}")
        assert resp.status_code == 403
        assert db.session.get(Report, report.id) is not None  # nothing was removed


def test_delete_unknown_report_returns_404_not_500(admin_client, app):
    resp = admin_client.delete("/api/reports/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reprocess invalidates stale verification
# ---------------------------------------------------------------------------

def test_reprocessing_an_approved_report_revokes_its_verification(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path, mismatch=False)
    approve_resp = admin_client.post(f"/api/reports/{report.id}/approve")
    assert approve_resp.get_json()["data"]["approval_status"] == "approved"

    resp = admin_client.post(f"/api/reports/{report.id}/process")
    assert resp.status_code == 200
    assert resp.get_json()["invalidated_approval"] is True

    db.session.refresh(report)
    assert report.approval_status == "pending"
    assert report.approved_by_id is None


def test_reprocessing_an_unapproved_report_does_not_falsely_report_invalidation(admin_client, app, tmp_path):
    report = _seed_processed_report(app, tmp_path)
    resp = admin_client.post(f"/api/reports/{report.id}/process")
    assert resp.get_json()["invalidated_approval"] is False
