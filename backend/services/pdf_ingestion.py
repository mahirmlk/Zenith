"""Bounded text extraction for user-provided research PDFs."""
from io import BytesIO

from pypdf import PdfReader

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_PAGE_TEXT_CHARS = 100_000
MAX_TOTAL_TEXT_CHARS = 2_000_000


class PdfIngestionError(ValueError):
    """The upload is invalid, encrypted, or exceeds extraction limits."""


def extract_pdf_pages(data: bytes) -> list[dict[str, int | str]]:
    """Extract page text with stable 1-based page numbers and bounded content."""
    if not data or len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
        raise PdfIngestionError("Upload must be a valid PDF no larger than 20 MiB")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise PdfIngestionError("Password-protected PDFs are not supported")
        if len(reader.pages) == 0 or len(reader.pages) > MAX_PDF_PAGES:
            raise PdfIngestionError("PDF must contain between 1 and 500 pages")
        pages: list[dict[str, int | str]] = []
        total_chars = 0
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len(text) > MAX_PAGE_TEXT_CHARS:
                raise PdfIngestionError("A PDF page exceeds the text extraction limit")
            total_chars += len(text)
            if total_chars > MAX_TOTAL_TEXT_CHARS:
                raise PdfIngestionError("PDF text exceeds the extraction limit")
            pages.append({"page_number": page_number, "text": text})
        return pages
    except PdfIngestionError:
        raise
    except Exception as exc:
        raise PdfIngestionError("PDF could not be parsed") from exc
