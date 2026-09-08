from app.extensions import db
from app.models.mixins import ConfidenceMixin, TimestampMixin


class Bond(TimestampMixin, ConfidenceMixin, db.Model):
    __tablename__ = "bonds"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    isin = db.Column(db.String(20), nullable=True, index=True)
    status = db.Column(db.String(30), nullable=True)  # e.g. Listed, Matured
    security = db.Column(db.String(160), nullable=False)
    bond_type = db.Column(db.String(20), default="government")  # government, corporate
    maturity_date = db.Column(db.Date, nullable=True, index=True)
    tenor = db.Column(db.String(40), nullable=True)
    coupon = db.Column(db.Numeric(9, 4), nullable=True)
    close_price = db.Column(db.Numeric(14, 4), nullable=True)
    previous_value = db.Column(db.Numeric(14, 4), nullable=True)
    bids = db.Column(db.Numeric(14, 4), nullable=True)
    offers = db.Column(db.Numeric(14, 4), nullable=True)
    # The real report's trailing "Bond traded" column is a VOLUME (0.00 if untraded,
    # a real figure like 52,000,000 if traded that day), not a yes/no flag — an earlier
    # version of this parser discarded that number and derived a always-True boolean
    # instead. traded_volume holds the real figure; bond_traded is now correctly derived
    # from it (> 0) rather than always defaulting True.
    traded_volume = db.Column(db.Numeric(20, 2), nullable=True)
    bond_traded = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f"<Bond {self.security} report={self.report_id}>"
