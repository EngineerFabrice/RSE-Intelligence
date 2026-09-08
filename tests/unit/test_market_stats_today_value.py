"""Regression test: a real report presents shares traded / equity turnover / number of
deals as a 'Previous / Today / Points / %Change' mini-table. The original regex grabbed
the FIRST number after the label (Previous, always 0.00 in every observed real report),
not the correct 'Today' value. See app/ingestion/parsers/market_stats_parser.py."""

from app.ingestion.parsers.market_stats_parser import parse_market_statistics
from app.ingestion.text_extraction import PageText


def test_grabs_today_value_not_previous_from_trading_stat_table():
    text = (
        "MARKET STATISTICS\n"
        "Shares traded               0.00     21,700     21,700   100.00\n"
        "Equity Turnover     0.00 14,307,500  14,307,600  100.00\n"
        "Number of deals     0.00     4.00      4.00  100.00\n"
        "Market Capitalization (Frw)                    6,634,919,683,716\n"
    )
    record = parse_market_statistics([PageText(1, text)])
    assert record is not None
    assert record.fields["shares_traded"] == 21700
    assert record.fields["equity_turnover"] == 14307500
    assert record.fields["number_of_deals"] == 4
    assert record.fields["market_capitalization"] == 6634919683716


def test_simple_label_value_format_still_works():
    text = "Shares Traded: 21,700\nEquity Turnover: 14,307,500\nNumber of Deals: 15\n"
    record = parse_market_statistics([PageText(1, text)])
    assert record.fields["shares_traded"] == 21700
    assert record.fields["number_of_deals"] == 15


def test_narrative_fallback_used_when_table_absent():
    text = (
        "Today's trading session recorded a turnover of Frw 206,685,500 worth of "
        "bonds traded in 5 deals on the fixed-income market and Frw 14,307,500 "
        "from 21,700 shares traded in 4 deals on the equities market."
    )
    record = parse_market_statistics([PageText(1, text)])
    assert record is not None
    assert record.fields["shares_traded"] == 21700
    assert record.fields["equity_turnover"] == 14307500
    assert record.fields["bond_turnover"] == 206685500
    assert record.fields["number_of_deals"] == 4
    # Narrative-sourced fields are routed to review, not silently treated as clean.
    assert record.field_valid["shares_traded"] is False
