from app.extensions import db
from app.models.mixins import ConfidenceMixin, TimestampMixin


class ClosingBellEntry(TimestampMixin, ConfidenceMixin, db.Model):
    __tablename__ = "closing_bell"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    security = db.Column(db.String(160), nullable=False)
    bid_quantity = db.Column(db.BigInteger, nullable=True)
    bid_price = db.Column(db.Numeric(14, 4), nullable=True)
    offer_quantity = db.Column(db.BigInteger, nullable=True)
    offer_price = db.Column(db.Numeric(14, 4), nullable=True)
    has_bid = db.Column(db.Boolean, default=False)
    has_offer = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), nullable=True)  # e.g. "No Bid", "No Offer", "Active"

    def __repr__(self):
        return f"<ClosingBellEntry {self.security} report={self.report_id}>"
