from app.extensions import db
from app.models.mixins import TimestampMixin


class AuditLog(TimestampMixin, db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(60), nullable=False)  # login, upload, approve, export, ...
    entity_type = db.Column(db.String(60), nullable=True)  # report, user, equity, ...
    entity_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<AuditLog {self.action} by user={self.user_id}>"
