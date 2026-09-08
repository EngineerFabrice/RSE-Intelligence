from app.ingestion.reconciliation import reconcile_report
from app.models.equity import Equity
from app.models.market_statistics import MarketStatistics
from app.models.report import Report


def _make_report(db):
    report = Report(filename="x.pdf", original_filename="x.pdf", file_hash="abc", storage_path="/tmp/x.pdf")
    db.session.add(report)
    db.session.commit()
    return report


def test_reconciliation_flags_mismatched_shares_traded(app, db):
    report = _make_report(db)
    db.session.add_all([
        Equity(report_id=report.id, symbol="BOK", volume=21600),
        Equity(report_id=report.id, symbol="BLR", volume=100),
    ])
    db.session.add(MarketStatistics(report_id=report.id, shares_traded=99999))
    db.session.commit()
    db.session.refresh(report)

    issues = reconcile_report(report)
    assert any(i["field"] == "shares_traded" for i in issues)


def test_reconciliation_passes_when_totals_match(app, db):
    report = _make_report(db)
    db.session.add_all([
        Equity(report_id=report.id, symbol="BOK", volume=21600),
        Equity(report_id=report.id, symbol="BLR", volume=100),
    ])
    db.session.add(MarketStatistics(report_id=report.id, shares_traded=21700))
    db.session.commit()
    db.session.refresh(report)

    issues = reconcile_report(report)
    assert not any(i["field"] == "shares_traded" for i in issues)


def test_reconciliation_skips_when_no_market_statistics(app, db):
    report = _make_report(db)
    db.session.add(Equity(report_id=report.id, symbol="BOK", volume=21600))
    db.session.commit()
    db.session.refresh(report)

    assert reconcile_report(report) == []
