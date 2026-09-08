from app.extensions import db
from app.models.mixins import TimestampMixin


class ExtractionRecord(TimestampMixin, db.Model):
    """Field-level data lineage: what value came from where, how, and with what confidence (spec §14)."""

    __tablename__ = "extraction_records"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    target_table = db.Column(db.String(60), nullable=False)  # e.g. "equities"
    target_id = db.Column(db.Integer, nullable=True)  # populated once the target row exists
    field_name = db.Column(db.String(80), nullable=False)

    value = db.Column(db.Text, nullable=True)
    source_page = db.Column(db.Integer, nullable=True)
    source_section = db.Column(db.String(80), nullable=True)
    source_text = db.Column(db.Text, nullable=True)
    extraction_method = db.Column(db.String(40), nullable=True)  # native_text, table_parser, ocr
    confidence = db.Column(db.Float, nullable=True)
    validation_status = db.Column(db.String(20), default="pending")  # pending, passed, failed

    def __repr__(self):
        return f"<ExtractionRecord {self.target_table}.{self.field_name} report={self.report_id}>"
