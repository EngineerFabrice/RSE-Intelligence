from app.extensions import db
from app.models.mixins import TimestampMixin

PROCESSING_STATUSES = (
    "uploaded",
    "processing",
    "extracted",
    "validation_required",
    "review_required",
    "approved",
    "failed",
    "archived",
)


class Report(TimestampMixin, db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    report_date = db.Column(db.Date, nullable=True, index=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    # Editable administrative metadata (spec: Update). original_filename is left
    # untouched as immutable upload provenance; display_name is what an admin renames
    # via Edit, falling back to original_filename when unset.
    display_name = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(120), default="Official RSE Market Report")
    file_hash = db.Column(db.String(64), nullable=False, index=True)
    storage_path = db.Column(db.String(500), nullable=False)
    file_size_bytes = db.Column(db.Integer, nullable=True)

    upload_time = db.Column(db.DateTime, nullable=True)
    processing_status = db.Column(db.String(30), nullable=False, default="uploaded")
    processing_step = db.Column(db.String(120), nullable=True)
    processing_error = db.Column(db.Text, nullable=True)

    validation_status = db.Column(db.String(30), nullable=False, default="pending")
    # pending, passed, issues_found
    approval_status = db.Column(db.String(30), nullable=False, default="pending")
    # pending, approved, rejected

    overall_confidence = db.Column(db.Float, nullable=True)
    extraction_version = db.Column(db.String(20), default="v1")
    layout_confidence = db.Column(db.Float, nullable=True)
    is_new_format = db.Column(db.Boolean, default=False)

    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])

    equities = db.relationship("Equity", backref="report", lazy="dynamic", cascade="all, delete-orphan")
    indices = db.relationship("MarketIndex", backref="report", lazy="dynamic", cascade="all, delete-orphan")
    market_statistics = db.relationship(
        "MarketStatistics", backref="report", uselist=False, cascade="all, delete-orphan"
    )
    exchange_rates = db.relationship("ExchangeRate", backref="report", lazy="dynamic", cascade="all, delete-orphan")
    bonds = db.relationship("Bond", backref="report", lazy="dynamic", cascade="all, delete-orphan")
    bond_trades = db.relationship("BondTrade", backref="report", lazy="dynamic", cascade="all, delete-orphan")
    closing_bell_entries = db.relationship(
        "ClosingBellEntry", backref="report", lazy="dynamic", cascade="all, delete-orphan"
    )
    extraction_records = db.relationship(
        "ExtractionRecord", backref="report", lazy="dynamic", cascade="all, delete-orphan"
    )
    validation_issues = db.relationship(
        "ValidationIssue", backref="report", lazy="dynamic", cascade="all, delete-orphan"
    )

    def is_locked(self) -> bool:
        """Approved reports have their source data locked from silent edits (spec §31)."""
        return self.approval_status == "approved"

    def open_issue_count(self) -> int:
        return self.validation_issues.filter_by(resolution=None).count()

    @property
    def name(self) -> str:
        return self.display_name or self.original_filename

    def total_extracted_records(self) -> int:
        """Count of extracted rows across every section — used for the admin Report
        Management list (spec: 'Number of extracted records')."""
        count = self.equities.count() + self.indices.count() + self.exchange_rates.count()
        count += self.bonds.count() + self.bond_trades.count() + self.closing_bell_entries.count()
        if self.market_statistics is not None:
            count += 1
        return count

    def status_label(self):
        """A single, explicit verification state for display — never a confidence
        percentage (spec §14: communicate data quality through explicit states)."""
        if self.processing_status == "failed":
            return "Failed", "failed"
        if self.processing_status == "processing":
            return "Processing", "processing"
        if self.approval_status == "approved":
            return "Verified", "approved"
        if self.processing_status == "review_required":
            return "Review Required", "review_required"
        if self.processing_status in ("validation_required", "extracted"):
            return "Processed", "validation_required"
        if self.processing_status == "archived":
            return "Archived", "archived"
        return "Uploaded", "uploaded"

    def __repr__(self):
        return f"<Report {self.id} {self.report_date} {self.processing_status}>"
