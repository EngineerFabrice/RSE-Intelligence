from app.extensions import db
from app.models.mixins import TimestampMixin

SEVERITIES = ("critical", "warning", "informational")
ISSUE_TYPES = ("conflict", "missing_field", "format_error", "out_of_range", "ocr_used", "new_layout",
               "narrative_source")


class ValidationIssue(TimestampMixin, db.Model):
    __tablename__ = "validation_issues"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    issue_type = db.Column(db.String(30), nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="warning")

    target_table = db.Column(db.String(60), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    field = db.Column(db.String(80), nullable=True)
    record_label = db.Column(db.String(160), nullable=True)  # e.g. symbol/ISIN for display

    expected_value = db.Column(db.Text, nullable=True)
    extracted_value = db.Column(db.Text, nullable=True)
    alternative_value = db.Column(db.Text, nullable=True)
    source_a_label = db.Column(db.String(120), nullable=True)
    source_a_page = db.Column(db.Integer, nullable=True)
    source_b_label = db.Column(db.String(120), nullable=True)
    source_b_page = db.Column(db.Integer, nullable=True)

    description = db.Column(db.Text, nullable=True)

    resolution = db.Column(db.String(30), nullable=True)  # chosen_a, chosen_b, corrected, dismissed
    resolved_value = db.Column(db.Text, nullable=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolution_reason = db.Column(db.Text, nullable=True)

    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])

    def is_open(self) -> bool:
        return self.resolution is None

    def __repr__(self):
        return f"<ValidationIssue {self.issue_type}/{self.severity} report={self.report_id}>"


class Correction(TimestampMixin, db.Model):
    """Immutable history of manual corrections to previously extracted values (spec §58)."""

    __tablename__ = "corrections"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)
    target_table = db.Column(db.String(60), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    field = db.Column(db.String(80), nullable=False)

    original_value = db.Column(db.Text, nullable=True)
    corrected_value = db.Column(db.Text, nullable=True)
    reason = db.Column(db.String(120), nullable=True)
    source_reference = db.Column(db.String(120), nullable=True)  # e.g. "Page 2"

    corrected_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    corrected_by = db.relationship("User", foreign_keys=[corrected_by_id])

    def __repr__(self):
        return f"<Correction {self.target_table}.{self.field} report={self.report_id}>"
