from app.extensions import db
from app.models.mixins import ConfidenceMixin, TimestampMixin


class BondTrade(TimestampMixin, ConfidenceMixin, db.Model):
    __tablename__ = "bond_trades"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    trade_date = db.Column(db.Date, nullable=True, index=True)
    isin = db.Column(db.String(20), nullable=True, index=True)
    security = db.Column(db.String(160), nullable=True)
    price_yield = db.Column(db.Numeric(14, 4), nullable=True)
    volume = db.Column(db.BigInteger, nullable=True)
    value = db.Column(db.Numeric(20, 2), nullable=True)
    number_of_trades = db.Column(db.Integer, nullable=True)

    def __repr__(self):
        return f"<BondTrade {self.isin} report={self.report_id}>"
