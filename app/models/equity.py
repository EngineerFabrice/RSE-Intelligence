from app.extensions import db
from app.models.mixins import ConfidenceMixin, TimestampMixin


class Equity(TimestampMixin, ConfidenceMixin, db.Model):
    __tablename__ = "equities"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    isin = db.Column(db.String(20), nullable=True, index=True)
    symbol = db.Column(db.String(20), nullable=False, index=True)
    security_name = db.Column(db.String(160), nullable=True)

    high_12m = db.Column(db.Numeric(18, 4), nullable=True)
    low_12m = db.Column(db.Numeric(18, 4), nullable=True)
    today_high = db.Column(db.Numeric(18, 4), nullable=True)
    today_low = db.Column(db.Numeric(18, 4), nullable=True)
    closing_price = db.Column(db.Numeric(18, 4), nullable=True)
    previous_close = db.Column(db.Numeric(18, 4), nullable=True)
    change = db.Column(db.Numeric(18, 4), nullable=True)
    change_percent = db.Column(db.Numeric(9, 4), nullable=True)
    volume = db.Column(db.BigInteger, nullable=True)
    value_turnover = db.Column(db.Numeric(20, 2), nullable=True)

    def __repr__(self):
        return f"<Equity {self.symbol} report={self.report_id}>"
