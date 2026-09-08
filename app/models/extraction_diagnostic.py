from app.extensions import db
from app.models.mixins import TimestampMixin


class ExtractionDiagnostic(TimestampMixin, db.Model):
    """Per-report, per-section extraction observability (spec §7): makes extraction
    failures inspectable instead of a bare 'No data extracted for this section.'

    Deliberately a new, additive table — nothing about the existing schema changes, so
    `db.create_all()` can add it to an existing database without touching current data.
    """

    __tablename__ = "extraction_diagnostics"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    section = db.Column(db.String(60), nullable=False)
    pages = db.Column(db.String(60), nullable=True)
    extraction_method = db.Column(db.String(40), nullable=True)

    tables_detected = db.Column(db.Integer, default=0)
    tables_used = db.Column(db.Integer, default=0)
    raw_rows = db.Column(db.Integer, default=0)
    accepted_rows = db.Column(db.Integer, default=0)
    rejected_rows = db.Column(db.Integer, default=0)
    records_persisted = db.Column(db.Integer, default=0)

    rejection_reasons = db.Column(db.Text, nullable=True)  # JSON list of {page, raw, reason}
    notes = db.Column(db.Text, nullable=True)

    report = db.relationship("Report", backref=db.backref(
        "diagnostics", lazy="dynamic", cascade="all, delete-orphan"
    ))

    def __repr__(self):
        return f"<ExtractionDiagnostic {self.section} report={self.report_id} accepted={self.accepted_rows}>"
