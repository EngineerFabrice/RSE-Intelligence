"""Tests for the presentation-only progress mapping used by the upload UI (spec: a
minimal determinate progress bar driven by real backend state, not a fake timer)."""

from types import SimpleNamespace

from app.services.progress import compute_progress


def _report(processing_status, processing_step=None):
    return SimpleNamespace(processing_status=processing_status, processing_step=processing_step)


def test_uploaded_status_is_near_zero():
    p = compute_progress(_report("uploaded"))
    assert p["state"] == "uploading"
    assert 0 <= p["percent"] < 10


def test_intermediate_step_maps_to_a_percent_between_0_and_100():
    p = compute_progress(_report("processing", "Equities identified"))
    assert p["state"] == "processing"
    assert 0 < p["percent"] < 100


def test_progress_percent_increases_monotonically_through_the_real_pipeline_order():
    from app.services.progress import _STEP_PERCENT

    steps = [
        "Document verified", "Text extracted", "Tables detected", "Sections classified",
        "Equities identified", "Bonds identified", "Market statistics identified",
        "Exchange rates identified", "Cross-validation running", "Finalizing report",
    ]
    percents = [_STEP_PERCENT[s] for s in steps]
    assert percents == sorted(percents)


def test_terminal_success_statuses_reach_100_only_after_processing():
    for status in ("review_required", "validation_required", "approved"):
        p = compute_progress(_report(status, "Finalizing report"))
        assert p["percent"] == 100
        assert p["state"] == "done"


def test_failed_status_is_a_distinct_error_state_not_a_percentage():
    p = compute_progress(_report("failed", "Processing failed"))
    assert p["state"] == "failed"


def test_unknown_step_does_not_crash_and_stays_in_processing_range():
    p = compute_progress(_report("processing", "Some future step not yet mapped"))
    assert p["state"] == "processing"
    assert 0 < p["percent"] < 100
