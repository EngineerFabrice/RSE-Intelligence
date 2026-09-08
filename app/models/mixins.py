from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ConfidenceMixin:
    """Shared confidence/traceability fields for extracted market records."""

    confidence_score = db.Column(db.Float, nullable=True)  # 0.0 - 1.0
    confidence_level = db.Column(db.String(20), default="review_required", nullable=False)
    # one of: high, review_required, manual_correction
    source_page = db.Column(db.Integer, nullable=True)
    source_section = db.Column(db.String(80), nullable=True)
    extraction_method = db.Column(db.String(40), nullable=True)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
