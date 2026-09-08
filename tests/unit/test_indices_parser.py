"""Regression tests for the indices parser. A real uploaded report's chart-caption text
('RWANDA SHARE INDEX') contains 'index' as a substring, which — combined with the
fragment-merge in table_extraction.py folding that caption into the neighboring bonds
table — made the old alias-only check misread the entire bonds table as index data (19
garbage records). See app/ingestion/parsers/indices_parser.py."""

from app.ingestion.parsers.indices_parser import parse_indices_from_tables, parse_indices_from_text
from app.ingestion.table_extraction import ExtractedTable
from app.ingestion.text_extraction import PageText


def test_chart_caption_does_not_produce_bogus_index_rows():
    # A caption fragment merged in front of an unrelated bonds table.
    table = ExtractedTable(1, [
        ["RWANDA SHARE INDEX chart", "RWANDA ALL SHARE INDEX chart"],
        ["ISIN-CODE", "Status", "Security", "Maturity", "Coupon", "Close", "Prev", "Bids", "Offers", "Traded"],
        ["RW000A182K48 FXD2/2016/15Yrs 09/05/2031 13.5% 103.00 103.00 0.00 0.00 0.00", "", "", "", "", "", "", "", "", ""],
    ])
    records, rejected = parse_indices_from_tables([table])
    assert records == []


def test_real_indices_table_still_parses():
    table = ExtractedTable(1, [
        ["INDICES", "Previous", "Today", "Points", "Change %"],
        ["RSI", "214.08", "215.00", "0.92", "0.43"],
        ["ALSI", "259.21", "260.00", "0.79", "0.30"],
    ])
    records, rejected = parse_indices_from_tables([table])
    names = {r.fields["index_name"] for r in records}
    assert names == {"RSI", "ALSI"}


def test_text_regex_prefers_today_over_previous_when_no_percent_sign():
    page = PageText(1, "RSI 214.08 215.50 +1.42 +0.66")
    records = parse_indices_from_text([page])
    rsi = next(r for r in records if r.fields["index_name"] == "RSI")
    assert rsi.fields["previous_value"] == 214.08
    assert rsi.fields["current_value"] == 215.50


def test_text_regex_single_value_with_percent_format():
    page = PageText(1, "RSI: 132.45 (1.20%)")
    records = parse_indices_from_text([page])
    rsi = next(r for r in records if r.fields["index_name"] == "RSI")
    assert rsi.fields["current_value"] == 132.45
    assert rsi.fields["percentage_change"] == 1.20
