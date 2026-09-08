from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.forms import LoginForm
from app.models.user import User
from app.services.audit import log_action

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    error = None
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.status == "active" and user.check_password(form.password.data):
            login_user(user)
            log_action("login", entity_type="user", entity_id=user.id, description=f"{user.email} signed in")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard.index"))
        error = "Invalid email or password, or the account is disabled."

    return render_template("auth/login.html", form=form, error=error)


@auth_bp.route("/logout")
@login_required
def logout():
    log_action("logout", entity_type="user", entity_id=current_user.id, description=f"{current_user.email} signed out")
    logout_user()
    return redirect(url_for("auth.login"))
