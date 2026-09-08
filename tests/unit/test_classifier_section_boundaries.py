"""Regression test: a real uploaded report was misclassified because the 'bond_trades'
keyword (no trailing word boundary) matched the 'Bond traded' Yes/No COLUMN HEADER that
appears inside the Government/Corporate Bonds tables, making the pipeline believe there
was a second, distinct bond-trades section that didn't actually exist — producing 17
duplicate/garbage bond-trade records. See app/ingestion/classifier.py."""

from app.ingestion.classifier import classify_document
from app.ingestion.text_extraction import PageText


def test_bond_traded_column_header_does_not_trigger_bond_trades_section():
    page = PageText(1, "Government Bonds\nISIN Status Security Maturity Coupon Close Prev Bids Offers Bond traded")
    result = classify_document([page])
    assert "bond_trades" not in result.sections
    assert "bonds" in result.sections


def test_genuine_bond_trades_heading_is_still_detected():
    page = PageText(1, "BOND TRADES\nTrade Date ISIN Security Price Volume Value")
    result = classify_document([page])
    assert "bond_trades" in result.sections


def test_bonds_traded_plural_heading_is_still_detected():
    page = PageText(1, "BONDS TRADED TODAY\nISIN Security Volume")
    result = classify_document([page])
    assert "bond_trades" in result.sections
