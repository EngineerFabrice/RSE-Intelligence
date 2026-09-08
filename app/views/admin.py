from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.auth.decorators import roles_required
from app.auth.forms import UserForm
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.report import Report
from app.models.user import ROLES, User
from app.services.audit import log_action

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/users", methods=["GET", "POST"])
@login_required
@roles_required("administrator")
def users():
    form = UserForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data.lower().strip()).first():
            flash("A user with that email already exists.", "danger")
        else:
            role = request.form.get("role", "viewer")
            if role not in ROLES:
                role = "viewer"
            user = User(name=form.name.data.strip(), email=form.email.data.lower().strip(), role=role)
            user.set_password(form.password.data or "changeme123")
            db.session.add(user)
            db.session.commit()
            log_action("create_user", entity_type="user", entity_id=user.id, description=f"Created {user.email}")
            flash(f"User {user.email} created.", "success")
        return redirect(url_for("admin.users"))

    all_users = User.query.order_by(User.name).all()
    return render_template("admin/users.html", form=form, users=all_users, roles=ROLES)


@admin_bp.route("/users/<int:user_id>/toggle-status", methods=["POST"])
@login_required
@roles_required("administrator")
def toggle_user_status(user_id):
    user = db.session.get(User, user_id)
    if user and user.id != current_user.id:
        user.status = "disabled" if user.status == "active" else "active"
        db.session.commit()
        log_action("update_user_status", entity_type="user", entity_id=user.id, description=user.status)
        flash(f"{user.email} is now {user.status}.", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/audit-log")
@login_required
@roles_required("administrator")
def audit_log():
    page = request.args.get("page", 1, type=int)
    per_page = 50
    query = AuditLog.query.order_by(AuditLog.id.desc())
    total = query.count()
    entries = query.offset((page - 1) * per_page).limit(per_page).all()
    return render_template("admin/audit_log.html", entries=entries, page=page,
                            total_pages=(total + per_page - 1) // per_page)


@admin_bp.route("/data-quality")
@login_required
def data_quality():
    total = Report.query.count()
    approved = Report.query.filter_by(approval_status="approved").count()
    needs_review = Report.query.filter_by(processing_status="review_required").count()
    failed = Report.query.filter_by(processing_status="failed").count()
    confidences = [r.overall_confidence for r in Report.query.filter(Report.overall_confidence.isnot(None)).all()]
    avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
    reports = Report.query.order_by(Report.id.desc()).limit(20).all()
    return render_template("admin/data_quality.html", total=total, approved=approved, needs_review=needs_review,
                            failed=failed, avg_confidence=avg_confidence, reports=reports)
