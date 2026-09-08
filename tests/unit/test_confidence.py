from app.ingestion.confidence import HIGH, MANUAL_CORRECTION, REVIEW_REQUIRED, average_score, score_field, worst_level


def test_score_field_clean_extraction_is_high():
    level, score = score_field(is_valid=True)
    assert level == HIGH
    assert score > 0.9


def test_score_field_missing_required_is_manual_correction():
    level, _ = score_field(is_valid=True, is_missing_required=True)
    assert level == MANUAL_CORRECTION


def test_score_field_conflict_is_review_required():
    level, _ = score_field(is_valid=True, has_conflict=True)
    assert level == REVIEW_REQUIRED


def test_score_field_ocr_is_review_required():
    level, _ = score_field(is_valid=True, was_ocr=True)
    assert level == REVIEW_REQUIRED


def test_worst_level_picks_lowest_confidence():
    assert worst_level([HIGH, HIGH]) == HIGH
    assert worst_level([HIGH, REVIEW_REQUIRED]) == REVIEW_REQUIRED
    assert worst_level([HIGH, REVIEW_REQUIRED, MANUAL_CORRECTION]) == MANUAL_CORRECTION


def test_average_score_ignores_none():
    assert average_score([1.0, None, 0.5]) == 0.75
    assert average_score([]) is None
