from functools import wraps

from flask import abort, jsonify, request
from flask_login import current_user


def roles_required(*roles):
    """Restrict a view to the given roles (spec §33). Administrator is always allowed."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.path.startswith("/api/"):
                    return jsonify(status="error", code="unauthorized", message="Authentication required."), 401
                abort(403)
            if current_user.role != "administrator" and current_user.role not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(status="error", code="forbidden",
                                    message="You do not have permission to do that."), 403
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def can_edit_required(view):
    return roles_required("administrator", "analyst", "reviewer")(view)


def can_approve_required(view):
    return roles_required("administrator", "reviewer")(view)
