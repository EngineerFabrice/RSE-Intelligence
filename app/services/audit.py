from flask import request
from flask_login import current_user

from app.extensions import db
from app.models.audit_log import AuditLog


def log_action(action: str, entity_type: str = None, entity_id: int = None, description: str = None):
    """Record an audit event (spec §32). Never raises — auditing must not break the calling workflow."""
    try:
        user_id = current_user.id if getattr(current_user, "is_authenticated", False) else None
        ip = request.remote_addr if request else None
        entry = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            ip_address=ip,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
