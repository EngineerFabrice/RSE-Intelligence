"""Translates internal pipeline processing steps into a user-facing progress percentage
and a short, non-technical status message.

This is presentation-only: it *reads* `report.processing_step` / `report.processing_status`
(already set by app/ingestion/pipeline.py, which is unchanged) and maps them to a number
and a plain-language sentence. The detailed step names (e.g. "Equities identified")
remain in the database for diagnostics/logging — this module exists so the upload UI can
show a real, backend-driven percentage without exposing that internal vocabulary to users.
"""

# Ordered so the mapping visually tracks the pipeline's actual sequence (see
# app/ingestion/pipeline.py) — the percentages are deliberately spaced to reflect that
# extraction (steps 3-9) is the bulk of the work, not upload/finalization.
_STEP_PERCENT = {
    "Document verified": 8,
    "Native text insufficient — attempting OCR": 15,
    "Text extracted": 22,
    "Tables detected": 32,
    "Sections classified": 42,
    "Equities identified": 55,
    "Bonds identified": 66,
    "Market statistics identified": 76,
    "Exchange rates identified": 85,
    "Cross-validation running": 93,
    "Finalizing report": 98,
}

_TERMINAL_SUCCESS_STATUSES = ("review_required", "validation_required", "approved")

# (percent threshold, message) — the highest threshold not exceeding the current
# percent wins. Deliberately generic language, no section/table/parser terminology.
_MESSAGES = (
    (0, "Uploading your report…"),
    (15, "Processing your report…"),
    (40, "Extracting market data…"),
    (78, "Validating data…"),
    (92, "Preparing your market report…"),
)


def _message_for_percent(percent: int) -> str:
    message = _MESSAGES[0][1]
    for threshold, text in _MESSAGES:
        if percent >= threshold:
            message = text
    return message


def compute_progress(report):
    """Returns {"percent": int, "message": str, "state": "uploading"|"processing"|"done"|"failed"}."""
    if report.processing_status == "failed":
        return {"percent": 0, "message": "We couldn't process this report.", "state": "failed"}

    if report.processing_status in _TERMINAL_SUCCESS_STATUSES:
        return {"percent": 100, "message": "Your market report is ready to preview.", "state": "done"}

    if report.processing_status == "uploaded":
        return {"percent": 3, "message": "Uploading your report…", "state": "uploading"}

    percent = _STEP_PERCENT.get(report.processing_step, 5)
    return {"percent": percent, "message": _message_for_percent(percent), "state": "processing"}
