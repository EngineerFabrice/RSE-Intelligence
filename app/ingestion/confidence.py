"""Confidence scoring engine (spec §10).

Confidence is never used to hide uncertainty — it drives whether a record is
auto-accepted (HIGH), routed to exception-based review (REVIEW_REQUIRED), or flagged
as unrecoverable by automation (MANUAL_CORRECTION).
"""

HIGH = "high"
REVIEW_REQUIRED = "review_required"
MANUAL_CORRECTION = "manual_correction"


def score_field(is_valid: bool, was_ocr: bool = False, has_conflict: bool = False,
                 is_missing_required: bool = False, is_unusual_format: bool = False):
    """Returns (level, numeric_score)."""
    if is_missing_required:
        return MANUAL_CORRECTION, 0.15

    if has_conflict:
        return REVIEW_REQUIRED, 0.45

    if not is_valid:
        return REVIEW_REQUIRED, 0.35

    if was_ocr:
        return REVIEW_REQUIRED, 0.70

    if is_unusual_format:
        return REVIEW_REQUIRED, 0.65

    return HIGH, 0.97


_LEVEL_RANK = {MANUAL_CORRECTION: 0, REVIEW_REQUIRED: 1, HIGH: 2}


def worst_level(levels):
    """Aggregate several field-level confidence levels into one record-level level."""
    levels = list(levels) or [HIGH]
    return min(levels, key=lambda lvl: _LEVEL_RANK.get(lvl, 0))


def average_score(scores):
    scores = [s for s in scores if s is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)
