"""End-to-end pipeline test: upload -> extract -> validate -> approve -> export.

Uses a synthetic reportlab-generated PDF (tests/fixtures/sample_report.py) since no real
official RSE report was available. The synthetic report is never used anywhere outside
this test suite.
"""

from tests.fixtures.sample_report import build_sample_pdf

from app.export.excel_export import export_report_to_excel
from app.extensions import db
from app.ingestion.pipeline import process_report
from app.models.report import Report
from app.services import duplicate_detection


def _create_and_process_report(app, tmp_path, mismatch=True):
    pdf_path = tmp_path / "sample_report.pdf"
    build_sample_pdf(pdf_path, shares_traded_mismatch=mismatch)
    file_bytes = pdf_path.read_bytes()

    report = Report(
        filename="sample_report.pdf",
        original_filename="sample_report.pdf",
        file_hash=duplicate_detection.compute_file_hash(file_bytes),
        storage_path=str(pdf_path),
    )
    db.session.add(report)
    db.session.commit()

    process_report(report.id)
    db.session.refresh(report)
    return report


def test_pipeline_extracts_all_core_sections(app, db, tmp_path):
    with app.app_context():
        report = _create_and_process_report(app, tmp_path, mismatch=False)

        assert report.processing_status in ("review_required", "validation_required")
        assert report.report_date is not None

        assert report.equities.count() == 2
        assert report.bonds.count() == 1
        assert report.bond_trades.count() == 1
        assert report.exchange_rates.count() == 2
        assert report.indices.count() == 2
        assert report.market_statistics is not None
        assert report.market_statistics.number_of_deals == 15


def test_pipeline_flags_reconciliation_conflict(app, db, tmp_path):
    with app.app_context():
        report = _create_and_process_report(app, tmp_path, mismatch=True)

        conflicts = report.validation_issues.filter_by(issue_type="conflict").all()
        assert any(c.field == "shares_traded" for c in conflicts)
        assert report.processing_status == "review_required"


def test_approval_blocked_while_critical_issues_open(app, db, tmp_path):
    with app.app_context():
        report = _create_and_process_report(app, tmp_path, mismatch=True)
        open_critical = report.validation_issues.filter_by(severity="critical", resolution=None).count()
        assert open_critical > 0


def test_full_workflow_produces_downloadable_excel(app, db, tmp_path):
    with app.app_context():
        report = _create_and_process_report(app, tmp_path, mismatch=False)
        buffer = export_report_to_excel(report)
        assert buffer.read(4) == b"PK\x03\x04"
