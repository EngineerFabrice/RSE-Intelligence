from flask import Blueprint, request
from flask_login import login_required

from app.api.utils import error, ok, to_dict
from app.extensions import db
from app.models.equity import Equity
from app.models.report import Report

equities_api_bp = Blueprint("equities_api", __name__)


def _latest_approved_subquery():
    """One row per symbol: the most recent approved report containing it."""
    return (
        db.session.query(Equity.symbol, db.func.max(Report.report_date).label("max_date"))
        .join(Report, Equity.report_id == Report.id)
        .filter(Report.approval_status == "approved")
        .group_by(Equity.symbol)
        .subquery()
    )


@equities_api_bp.route("", methods=["GET"])
@login_required
def list_equities():
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    sort = request.args.get("sort", "symbol")

    sub = _latest_approved_subquery()
    query = (
        db.session.query(Equity)
        .join(Report, Equity.report_id == Report.id)
        .join(sub, db.and_(Equity.symbol == sub.c.symbol, Report.report_date == sub.c.max_date))
        .filter(Report.approval_status == "approved")
    )
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(Equity.symbol.ilike(like), Equity.security_name.ilike(like)))

    sort_columns = {
        "symbol": Equity.symbol, "volume": Equity.volume.desc(),
        "change": Equity.change_percent.desc(), "value": Equity.value_turnover.desc(),
    }
    query = query.order_by(sort_columns.get(sort, Equity.symbol))

    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return ok({
        "items": [to_dict(e, exclude=("report_id",)) for e in items],
        "page": page, "per_page": per_page, "total": total,
    })


@equities_api_bp.route("/<string:symbol>", methods=["GET"])
@login_required
def get_equity(symbol):
    latest = (
        Equity.query.join(Report, Equity.report_id == Report.id)
        .filter(Equity.symbol == symbol.upper(), Report.approval_status == "approved")
        .order_by(Report.report_date.desc())
        .first()
    )
    if not latest:
        return error("Security not found.", "not_found", 404)
    data = to_dict(latest)
    data["report"] = to_dict(latest.report)
    return ok(data)


@equities_api_bp.route("/<string:symbol>/history", methods=["GET"])
@login_required
def get_equity_history(symbol):
    rows = (
        Equity.query.join(Report, Equity.report_id == Report.id)
        .filter(Equity.symbol == symbol.upper(), Report.approval_status == "approved")
        .order_by(Report.report_date.asc())
        .all()
    )
    history = [
        {
            "report_date": r.report.report_date.isoformat() if r.report.report_date else None,
            "closing_price": float(r.closing_price) if r.closing_price is not None else None,
            "volume": r.volume,
            "change_percent": float(r.change_percent) if r.change_percent is not None else None,
        }
        for r in rows
    ]
    return ok({"symbol": symbol.upper(), "history": history})
