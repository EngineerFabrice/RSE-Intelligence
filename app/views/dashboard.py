from flask import Blueprint, render_template
from flask_login import login_required

from app.models.report import Report
from app.services import insights

dashboard_bp = Blueprint("dashboard", __name__)

# (label, attribute) pairs used to summarize which sections of the latest verified
# report actually have extracted data — order matches how they read in the report
# preview itself.
_SECTION_ATTRS = (
    ("Equities", "equities"),
    ("Bonds", "bonds"),
    ("Bond Trades", "bond_trades"),
    ("Indices", "indices"),
    ("Exchange Rates", "exchange_rates"),
    ("Closing Bell", "closing_bell_entries"),
)


def _validated_sections(report):
    """Which sections of `report` actually produced data, with a row count each —
    used to show "Key validated sections" without claiming a section is present
    when nothing was extracted for it."""
    if report is None:
        return []
    sections = [(label, getattr(report, attr).count()) for label, attr in _SECTION_ATTRS]
    if report.market_statistics is not None:
        sections.append(("Market Statistics", 1))
    return [(label, count) for label, count in sections if count]


@dashboard_bp.route("/")
@login_required
def index():
    latest_report = Report.query.order_by(Report.id.desc()).first()

    # "Market Pulse" and "Latest Market Report" both read from the latest *approved*
    # report specifically (not just the latest upload) — approval is this platform's
    # explicit human sign-off that a report's figures are correct (spec §31), so it's
    # the only state worth calling "validated/canonical" on the home page.
    latest_verified = insights.latest_approved_report()

    recent_reports = (
        Report.query.order_by(Report.upload_time.desc().nullslast(), Report.id.desc()).limit(5).all()
    )

    platform_status = {
        "in_progress": Report.query.filter(Report.processing_status.in_(("uploaded", "processing"))).count(),
        "needs_review": Report.query.filter_by(processing_status="review_required").count(),
        "failed": Report.query.filter_by(processing_status="failed").count(),
    }

    return render_template(
        "dashboard.html",
        latest_report=latest_report,
        latest_verified=latest_verified,
        validated_sections=_validated_sections(latest_verified),
        recent_reports=recent_reports,
        platform_status=platform_status,
    )
