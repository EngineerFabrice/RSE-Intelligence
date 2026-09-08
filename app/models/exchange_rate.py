from app.extensions import db
from app.models.mixins import ConfidenceMixin, TimestampMixin


class ExchangeRate(TimestampMixin, ConfidenceMixin, db.Model):
    __tablename__ = "exchange_rates"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    currency = db.Column(db.String(10), nullable=False, index=True)  # USD, KES, UGX, BIF, TZS, ZAR, ...
    buy_rate = db.Column(db.Numeric(14, 4), nullable=True)
    sell_rate = db.Column(db.Numeric(14, 4), nullable=True)
    average_rate = db.Column(db.Numeric(14, 4), nullable=True)

    def __repr__(self):
        return f"<ExchangeRate {self.currency} report={self.report_id}>"
