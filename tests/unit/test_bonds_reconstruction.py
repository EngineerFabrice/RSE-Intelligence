"""Regression tests for the pattern-based bond-row reconstruction that tolerates the
optional 'Status' column (real reports print 'Re-opened' for some bonds and nothing for
others, which breaks any fixed left-to-right token position — see
app/ingestion/parsers/bonds_parser.py)."""

from app.ingestion.parsers.bonds_parser import _reconstruct_bond_row


def test_reconstructs_bond_row_with_status_present():
    tokens = "RW000A19HS6 Re-opened FXD2/2018/10Yrs 12/05/2028 12.50% 108.8 108.8 0.00 0.00 0.00".split()
    fields, reason = _reconstruct_bond_row(tokens)
    assert reason is None
    assert fields["isin"] == "RW000A19HS6"
    assert fields["status"] == "Re-opened"
    assert fields["security"] == "FXD2/2018/10Yrs"
    assert fields["maturity_date"] == "12/05/2028"
    assert fields["coupon"] == "12.50%"
    assert fields["close_price"] == "108.8"
    assert fields["previous_value"] == "108.8"
    assert fields["bids"] == "0.00"
    assert fields["offers"] == "0.00"
    assert fields["traded_volume"] == "0.00"


def test_captures_real_traded_volume_not_just_a_flag():
    # A bond that was actually traded that session — the trailing figure is a real
    # volume (52,000,000), not the boolean "yes/no" an earlier version discarded it as.
    tokens = "RW000A28UBB2 Re-opened FXD2/2020/15Yrs 02/02/2035 12.550% 100.8 100.85 0.00 0.00 52,000,000".split()
    fields, reason = _reconstruct_bond_row(tokens)
    assert reason is None
    assert fields["traded_volume"] == "52,000,000"


def test_reconstructs_bond_row_with_status_absent():
    tokens = "RW000A182K48 FXD2/2016/15Yrs 09/05/2031 13.5% 103.00 103.00 0.00 0.00 0.00".split()
    fields, reason = _reconstruct_bond_row(tokens)
    assert reason is None
    assert fields["isin"] == "RW000A182K48"
    assert fields["status"] is None
    assert fields["security"] == "FXD2/2016/15Yrs"
    assert fields["maturity_date"] == "09/05/2031"


def test_rejects_row_with_no_recognizable_maturity_date():
    tokens = "RW000A182K48 FXD2/2016/15Yrs NOTADATE 13.5% 103.00 103.00 0.00 0.00 0.00".split()
    fields, reason = _reconstruct_bond_row(tokens)
    assert fields is None
    assert "maturity" in reason.lower()


def test_rejects_row_with_bad_trailing_numerics():
    tokens = "RW000A182K48 FXD2/2016/15Yrs 09/05/2031 13.5% 103.00 103.00 0.00 0.00 N/A".split()
    fields, reason = _reconstruct_bond_row(tokens)
    assert fields is None
    assert "trailing" in reason.lower()


def test_rejects_row_that_is_too_short():
    fields, reason = _reconstruct_bond_row(["RW000A182K48", "103.00"])
    assert fields is None
    assert reason is not None
