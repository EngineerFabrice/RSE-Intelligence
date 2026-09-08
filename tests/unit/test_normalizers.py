from datetime import date

from app.ingestion.normalizers import (
    is_blank, parse_currency, parse_date, parse_integer, parse_number, parse_percentage,
    validate_isin,
)


def test_parse_number_thousands_separator():
    assert parse_number("21,600") == 21600.0


def test_parse_number_parenthesised_negative():
    assert parse_number("(1,250.50)") == -1250.50


def test_parse_number_blank_returns_none():
    assert parse_number("-") is None
    assert parse_number("") is None
    assert parse_number(None) is None


def test_parse_number_garbage_returns_none():
    assert parse_number("abc") is None


def test_parse_integer_rounds():
    assert parse_integer("1,000.6") == 1001


def test_parse_percentage():
    assert parse_percentage("12.5%") == 12.5


def test_parse_currency_strips_prefix():
    assert parse_currency("RWF 1,200.00") == 1200.0
    assert parse_currency("Frw 500") == 500.0


def test_parse_date_multiple_formats():
    assert parse_date("07 September 2026") == date(2026, 9, 7)
    assert parse_date("2026-09-07") == date(2026, 9, 7)
    assert parse_date("07/09/2026") == date(2026, 9, 7)


def test_parse_date_invalid_returns_none():
    assert parse_date("not a date") is None


def test_validate_isin_valid():
    # US0378331005 = Apple Inc. ISIN, a well-known valid checksum example.
    assert validate_isin("US0378331005") is True


def test_validate_isin_invalid_checksum():
    assert validate_isin("US0378331006") is False


def test_validate_isin_malformed():
    assert validate_isin("NOTANISIN") is False
    assert validate_isin("") is False
    assert validate_isin(None) is False


def test_is_blank():
    assert is_blank(None) is True
    assert is_blank("-") is True
    assert is_blank("  ") is True
    assert is_blank("BOK") is False
