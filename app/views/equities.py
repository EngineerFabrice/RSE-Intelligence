from flask import Blueprint, render_template
from flask_login import login_required

equities_bp = Blueprint("equities", __name__)


@equities_bp.route("/")
@login_required
def list_equities():
    return render_template("equities/list.html")


@equities_bp.route("/<string:symbol>")
@login_required
def equity_detail(symbol):
    return render_template("equities/detail.html", symbol=symbol.upper())
