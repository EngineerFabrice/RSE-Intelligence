from app.extensions import db
from app.models.mixins import ConfidenceMixin, TimestampMixin


class MarketStatistics(TimestampMixin, ConfidenceMixin, db.Model):
    __tablename__ = "market_statistics"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, unique=True, index=True)

    shares_traded = db.Column(db.BigInteger, nullable=True)
    equity_turnover = db.Column(db.Numeric(20, 2), nullable=True)
    bond_turnover = db.Column(db.Numeric(20, 2), nullable=True)
    number_of_deals = db.Column(db.Integer, nullable=True)
    market_capitalization = db.Column(db.Numeric(24, 2), nullable=True)
    repo_value = db.Column(db.Numeric(20, 2), nullable=True)
    repo_deals = db.Column(db.Integer, nullable=True)
    repo_tenor = db.Column(db.String(40), nullable=True)
    repo_rate = db.Column(db.Numeric(9, 4), nullable=True)

    def __repr__(self):
        return f"<MarketStatistics report={self.report_id}>"
