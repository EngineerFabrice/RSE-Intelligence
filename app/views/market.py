from flask import Blueprint, render_template
from flask_login import login_required

market_bp = Blueprint("market", __name__)


@market_bp.route("/indices")
@login_required
def indices():
    return render_template("market/indices.html")


@market_bp.route("/exchange-rates")
@login_required
def exchange_rates():
    return render_template("market/exchange_rates.html")


@market_bp.route("/closing-bell")
@login_required
def closing_bell():
    return render_template("market/closing_bell.html")


@market_bp.route("/analytics")
@login_required
def analytics():
    return render_template("market/analytics.html")
