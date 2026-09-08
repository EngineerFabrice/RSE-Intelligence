"""Stage 1 — native text extraction (spec §7)."""

import logging

logger = logging.getLogger("rse_intelligence.ingestion")


class PageText:
    def __init__(self, page_number: int, text: str):
        self.page_number = page_number
        self.text = text or ""

    @property
    def char_count(self):
        return len(self.text.strip())


def extract_native_text(pdf_path: str):
    """Returns (pages: list[PageText], metadata: dict). Never raises — an extraction
    failure yields an empty page list so the pipeline can fall back to OCR."""
    import fitz  # PyMuPDF

    pages = []
    metadata = {}
    try:
        with fitz.open(pdf_path) as doc:
            metadata = {
                "page_count": doc.page_count,
                "title": (doc.metadata or {}).get("title"),
                "producer": (doc.metadata or {}).get("producer"),
            }
            for i, page in enumerate(doc):
                pages.append(PageText(i + 1, page.get_text("text")))
    except Exception:
        logger.exception("Native text extraction failed for %s", pdf_path)
        return [], {}

    return pages, metadata


def total_extracted_chars(pages) -> int:
    return sum(p.char_count for p in pages)
