from app.extensions import db
from app.models.mixins import ConfidenceMixin, TimestampMixin


class MarketIndex(TimestampMixin, ConfidenceMixin, db.Model):
    """RSE indices such as RSI, ALSI. Table is 'indices' (class avoids clashing with sqlalchemy.Index)."""

    __tablename__ = "indices"

    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("reports.id"), nullable=False, index=True)

    index_name = db.Column(db.String(40), nullable=False, index=True)  # e.g. RSI, ALSI
    current_value = db.Column(db.Numeric(18, 4), nullable=True)
    previous_value = db.Column(db.Numeric(18, 4), nullable=True)
    change = db.Column(db.Numeric(18, 4), nullable=True)
    percentage_change = db.Column(db.Numeric(9, 4), nullable=True)

    def __repr__(self):
        return f"<MarketIndex {self.index_name} report={self.report_id}>"
