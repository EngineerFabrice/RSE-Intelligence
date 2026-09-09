from flask import Blueprint, render_template
from flask_login import login_required

from app.auth.decorators import roles_required

assistant_bp = Blueprint("assistant", __name__)


@assistant_bp.route("/")
@login_required
@roles_required("administrator", "analyst")
def index():
    return render_template("assistant/ask.html")
