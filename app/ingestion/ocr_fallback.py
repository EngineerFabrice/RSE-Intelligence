"""Stage 4 — OCR fallback for scanned PDFs (spec §7).

Degrades gracefully: if Tesseract isn't installed on the host machine, this returns an
explicit "unavailable" status rather than crashing the pipeline or silently returning
"Unable to extract text."
"""

import logging

from app.ingestion.text_extraction import PageText

logger = logging.getLogger("rse_intelligence.ingestion")


def ocr_is_available(tesseract_cmd: str = None) -> bool:
    try:
        import pytesseract

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def extract_text_via_ocr(pdf_path: str, tesseract_cmd: str = None):
    """Returns (pages: list[PageText], status: str) where status is one of
    'success', 'unavailable', 'failed'."""
    if not ocr_is_available(tesseract_cmd):
        logger.warning("OCR requested but Tesseract is not available on this machine.")
        return [], "unavailable"

    try:
        import pytesseract
        from pdf2image import convert_from_path

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        images = convert_from_path(pdf_path)
        pages = []
        for i, image in enumerate(images):
            text = pytesseract.image_to_string(image)
            pages.append(PageText(i + 1, text))
        return pages, "success"
    except Exception:
        logger.exception("OCR extraction failed for %s", pdf_path)
        return [], "failed"
