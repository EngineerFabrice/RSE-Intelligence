from flask import Blueprint, render_template
from flask_login import login_required

bonds_bp = Blueprint("bonds", __name__)


@bonds_bp.route("/")
@login_required
def list_bonds():
    return render_template("bonds/list.html")
