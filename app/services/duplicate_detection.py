import hashlib

from app.models.report import Report


def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def find_duplicate(file_hash: str, report_date=None):
    """Detect duplicate reports by file hash first, then by report date (spec §42)."""
    existing = Report.query.filter_by(file_hash=file_hash).first()
    if existing:
        return existing, "identical_file"

    if report_date is not None:
        existing = Report.query.filter_by(report_date=report_date).filter(
            Report.processing_status != "failed"
        ).first()
        if existing:
            return existing, "same_report_date"

    return None, None
