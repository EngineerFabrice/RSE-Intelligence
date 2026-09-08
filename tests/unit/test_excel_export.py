from datetime import date

from app.export.excel_export import build_workbook, export_report_to_excel
from app.models.bond import Bond
from app.models.equity import Equity
from app.models.exchange_rate import ExchangeRate
from app.models.index import MarketIndex
from app.models.market_statistics import MarketStatistics
from app.models.report import Report


def _make_report(db):
    report = Report(filename="x.pdf", original_filename="x.pdf", file_hash="abc", storage_path="/tmp/x.pdf",
                     source="Official RSE Market Report", report_date=date(2026, 9, 7))
    db.session.add(report)
    db.session.commit()
    return report


def _make_report_with_equity(db):
    report = _make_report(db)
    db.session.add(Equity(report_id=report.id, symbol="BOK", closing_price=660, volume=21600,
                           value_turnover=14256000, confidence_level="high"))
    db.session.commit()
    db.session.refresh(report)
    return report


def test_workbook_has_five_expected_sheets(app, db):
    report = _make_report_with_equity(db)
    wb = build_workbook(report)
    assert wb.sheetnames == ["STOCK", "MARKET STATS", "BONDS", "BONDS TRADES", "EXCHANGE RATE"]


def test_stock_sheet_matches_reference_layout(app, db):
    # Matches the organization's reference workbook: header at row 1, no metadata
    # preamble, columns SECURITY / CLOSING / VOLUME / VALUE only.
    report = _make_report_with_equity(db)
    wb = build_workbook(report)
    ws = wb["STOCK"]
    assert [c.value for c in ws[1]] == ["SECURITY", "CLOSING", "VOLUME", "VALUE"]
    assert [c.value for c in ws[2]] == ["BOK", 660.0, 21600, 14256000.0]


def test_market_stats_sheet_includes_indices_and_turnover(app, db):
    report = _make_report(db)
    db.session.add(MarketIndex(report_id=report.id, index_name="RSI", current_value=214.08))
    db.session.add(MarketStatistics(report_id=report.id, equity_turnover=14307500, bond_turnover=206685500,
                                     market_capitalization=6634919683716))
    db.session.commit()
    db.session.refresh(report)

    wb = build_workbook(report)
    ws = wb["MARKET STATS"]
    assert [c.value for c in ws[1]] == ["INDICATORS", "CLOSING"]
    rows = {row[0].value: row[1].value for row in ws.iter_rows(min_row=2)}
    assert rows["RSI"] == 214.08
    assert rows["Equity turnover"] == 14307500.0
    assert rows["Bond market today (FRW)"] == 206685500.0
    assert rows["Market capitalization (FRW)"] == 6634919683716.0


def test_bonds_sheet_numbers_rows_and_omits_unavailable_fields(app, db):
    report = _make_report(db)
    db.session.add(Bond(report_id=report.id, isin="RW000A182K48", security="FXD2/2016/15Yrs",
                         maturity_date=date(2031, 5, 9), coupon=13.5, close_price=103.0,
                         bond_type="government"))
    db.session.commit()
    db.session.refresh(report)

    wb = build_workbook(report)
    ws = wb["BONDS"]
    assert [c.value for c in ws[1]] == [
        "T-BONDS No", "ISIN-CODE", "ISSUE DATE", "MATURITY DATE", "COUPON RATE", "YIELD TM",
        "BOND CATEGORY", "CLOSING PRICE",
    ]
    data_row = [c.value for c in ws[2]]
    assert data_row[0] == 1  # sequential T-BONDS No
    assert data_row[1] == "RW000A182K48"
    assert data_row[2] is None  # issue date genuinely unavailable, never fabricated
    assert data_row[3] == date(2031, 5, 9)
    assert data_row[5] is None  # yield-to-maturity genuinely unavailable
    assert data_row[6] == "TREASURY"


def test_bonds_trades_sheet_only_includes_actually_traded_bonds(app, db):
    report = _make_report(db)
    db.session.add(Bond(report_id=report.id, isin="RW1", security="FXD1/2020/10Yrs", status="Re-opened",
                         close_price=100.8, previous_value=100.85, traded_volume=52000000,
                         bond_traded=True, bond_type="government"))
    db.session.add(Bond(report_id=report.id, isin="RW2", security="FXD2/2021/5Yrs",
                         close_price=101.0, previous_value=101.0, traded_volume=0,
                         bond_traded=False, bond_type="government"))
    db.session.commit()
    db.session.refresh(report)

    wb = build_workbook(report)
    ws = wb["BONDS TRADES"]
    assert [c.value for c in ws[1]] == ["BOND", "CATEGORY", "VOLUME", "PREVIOUS", "CLOSING", "CHANGE"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert len(rows) == 1  # the untraded bond is excluded
    assert rows[0][0] == "FXD1/2020/10Yrs (Re-opened)"
    assert rows[0][2] == 52000000.0
    assert round(rows[0][5], 2) == -0.05  # close - previous


def test_exchange_rate_sheet_has_no_average_column(app, db):
    report = _make_report(db)
    db.session.add(ExchangeRate(report_id=report.id, currency="USD", buy_rate=1466.39, sell_rate=1476.39))
    db.session.commit()
    db.session.refresh(report)

    wb = build_workbook(report)
    ws = wb["EXCHANGE RATE"]
    assert [c.value for c in ws[1]] == ["CURRENCY CODE", "BUYING VALUE", "SELLING VALUE"]
    assert [c.value for c in ws[2]] == ["USD", 1466.39, 1476.39]


def test_export_produces_valid_xlsx_bytes(app, db):
    report = _make_report_with_equity(db)
    buffer = export_report_to_excel(report)
    header = buffer.read(4)
    assert header == b"PK\x03\x04"  # xlsx is a zip archive
