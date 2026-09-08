"""Regression test for the narrative closing-bell parser, added because a real report's
Closing Bell section turned out to be 100% prose with no table at all (see
app/ingestion/parsers/closing_bell_parser.py)."""

from app.ingestion.text_extraction import PageText
from app.ingestion.parsers.closing_bell_parser import parse_closing_bell_from_text


def test_parses_bid_only_sentence():
    page = PageText(1, "On KCB counter, there were outstanding bids of 11,000 shares at Frw 500 and no offers.")
    records = parse_closing_bell_from_text([page])
    assert len(records) == 1
    f = records[0].fields
    assert f["security"] == "KCB"
    assert f["has_bid"] is True
    assert f["has_offer"] is False
    assert f["bid_quantity"] == 11000
    assert f["bid_price"] == 500


def test_parses_offer_only_sentence():
    page = PageText(1, "On BLR counter, there were outstanding offers of 50,000 shares at Frw 515 and no bids.")
    records = parse_closing_bell_from_text([page])
    assert len(records) == 1
    f = records[0].fields
    assert f["security"] == "BLR"
    assert f["has_offer"] is True
    assert f["has_bid"] is False
    assert f["offer_price"] == 515


def test_parses_price_range_as_midpoint():
    page = PageText(1, "On MTNR counter, there were outstanding bids of 120,000 shares between "
                       "Frw 130-135 and no offers.")
    records = parse_closing_bell_from_text([page])
    assert len(records) == 1
    assert records[0].fields["bid_price"] == 132.5


def test_multiple_sentences_on_one_page():
    text = (
        "On KCB counter, there were outstanding bids of 11,000 shares at Frw 500 and no offers. "
        "On IMR counter, there were outstanding bids of 60,000 shares at Frw 100 and no offers."
    )
    records = parse_closing_bell_from_text([PageText(1, text)])
    assert {r.fields["security"] for r in records} == {"KCB", "IMR"}


def test_unrelated_text_produces_no_records():
    page = PageText(1, "The market remained stable throughout the session.")
    assert parse_closing_bell_from_text([page]) == []
