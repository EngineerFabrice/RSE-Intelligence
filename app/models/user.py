from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models.mixins import TimestampMixin

ROLES = ("administrator", "analyst", "reviewer", "viewer")


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="viewer")
    status = db.Column(db.String(20), nullable=False, default="active")  # active, disabled

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.status == "active"

    def has_role(self, *roles) -> bool:
        return self.role in roles

    def can_edit(self) -> bool:
        return self.role in ("administrator", "analyst", "reviewer")

    def can_approve(self) -> bool:
        return self.role in ("administrator", "reviewer")

    def is_admin(self) -> bool:
        return self.role == "administrator"

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
