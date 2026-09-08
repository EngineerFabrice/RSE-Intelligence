from flask import Blueprint, request
from flask_login import login_required

from app.api.utils import error, ok, to_dict
from app.models.bond import Bond
from app.models.bond_trade import BondTrade
from app.models.report import Report

bonds_api_bp = Blueprint("bonds_api", __name__)


@bonds_api_bp.route("", methods=["GET"])
@login_required
def list_bonds():
    bond_type = request.args.get("type")
    year = request.args.get("maturity_year", type=int)

    query = Bond.query.join(Report, Bond.report_id == Report.id).filter(Report.approval_status == "approved")
    if bond_type:
        query = query.filter(Bond.bond_type == bond_type)
    if year:
        query = query.filter(db_extract_year(Bond.maturity_date) == year)
    query = query.order_by(Bond.maturity_date.asc().nullslast())

    return ok([to_dict(b) for b in query.all()])


def db_extract_year(column):
    from sqlalchemy import extract
    return extract("year", column)


@bonds_api_bp.route("/<string:isin>", methods=["GET"])
@login_required
def get_bond(isin):
    latest = (
        Bond.query.join(Report, Bond.report_id == Report.id)
        .filter(Bond.isin == isin, Report.approval_status == "approved")
        .order_by(Report.report_date.desc())
        .first()
    )
    if not latest:
        return error("Bond not found.", "not_found", 404)
    trades = (
        BondTrade.query.join(Report, BondTrade.report_id == Report.id)
        .filter(BondTrade.isin == isin, Report.approval_status == "approved")
        .order_by(BondTrade.trade_date.desc())
        .limit(50)
        .all()
    )
    data = to_dict(latest)
    data["recent_trades"] = [to_dict(t) for t in trades]
    return ok(data)


@bonds_api_bp.route("/trades", methods=["GET"])
@login_required
def list_bond_trades():
    query = (
        BondTrade.query.join(Report, BondTrade.report_id == Report.id)
        .filter(Report.approval_status == "approved")
        .order_by(BondTrade.trade_date.desc())
        .limit(200)
    )
    return ok([to_dict(t) for t in query.all()])
