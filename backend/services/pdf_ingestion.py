"""Bounded, local text extraction for user-provided research PDFs."""
from __future__ import annotations

import asyncio
import shutil
import time
from io import BytesIO

from pypdf import PdfReader

MAX_PDF_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_PAGE_TEXT_CHARS = 100_000
MAX_TOTAL_TEXT_CHARS = 2_000_000
MAX_OCR_PAGES = 5
OCR_RENDER_SCALE = 1.4  # approximately 100 DPI for standard PDF points
OCR_MAX_PIXELS = 8_000_000
OCR_PAGE_TIMEOUT_SECONDS = 6.0
OCR_TOTAL_TIMEOUT_SECONDS = 20.0


class PdfIngestionError(ValueError):
    """The upload is invalid, encrypted, or exceeds extraction limits."""


class PdfOcrUnavailableError(RuntimeError):
    """OCR was requested but its local runtime is not installed or configured."""


def _ocr_scanned_pages(data: bytes, page_indexes: list[int]) -> dict[int, tuple[str, str]]:
    """OCR only bounded scanned pages; returns zero-based index -> text, method."""
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise PdfOcrUnavailableError("Local OCR dependencies are unavailable") from exc

    command = getattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
    if not shutil.which(command):
        raise PdfOcrUnavailableError("Local Tesseract OCR is unavailable")

    deadline = time.monotonic() + OCR_TOTAL_TIMEOUT_SECONDS
    results: dict[int, tuple[str, str]] = {}
    attempted = 0
    try:
        document = fitz.open(stream=data, filetype="pdf")
        try:
            for page_index in page_indexes:
                if attempted >= MAX_OCR_PAGES or time.monotonic() >= deadline:
                    results[page_index] = ("", "ocr_limit")
                    continue

                page = document.load_page(page_index)
                bounds = page.rect
                width = max(1, round(bounds.width * OCR_RENDER_SCALE))
                height = max(1, round(bounds.height * OCR_RENDER_SCALE))
                if width * height > OCR_MAX_PIXELS:
                    results[page_index] = ("", "ocr_limit")
                    continue

                attempted += 1
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(OCR_RENDER_SCALE, OCR_RENDER_SCALE),
                    colorspace=fitz.csGRAY,
                    alpha=False,
                )
                remaining = deadline - time.monotonic()
                timeout = min(OCR_PAGE_TIMEOUT_SECONDS, remaining)
                if timeout <= 0:
                    results[page_index] = ("", "ocr_limit")
                    continue
                image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
                try:
                    text = pytesseract.image_to_string(image, timeout=timeout).strip()
                except RuntimeError as exc:
                    # pytesseract uses RuntimeError for subprocess timeouts.
                    if "timeout" in str(exc).casefold():
                        results[page_index] = ("", "ocr_limit")
                        continue
                    raise PdfIngestionError("Local OCR failed to process a scanned page") from exc
                results[page_index] = (text, "ocr" if text else "empty")
        finally:
            document.close()
    except PdfOcrUnavailableError:
        raise
    except Exception as exc:
        raise PdfIngestionError("Scanned PDF pages could not be processed") from exc
    return results


def extract_pdf_pages(
    data: bytes, *, ocr_enabled: bool = False
) -> list[dict[str, int | str]]:
    """Extract page text with stable citations and optional bounded local OCR."""
    if not data or len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
        raise PdfIngestionError("Upload must be a valid PDF no larger than 20 MiB")
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise PdfIngestionError("Password-protected PDFs are not supported")
        if len(reader.pages) == 0 or len(reader.pages) > MAX_PDF_PAGES:
            raise PdfIngestionError("PDF must contain between 1 and 500 pages")

        extracted: list[str] = []
        total_chars = 0
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if len(text) > MAX_PAGE_TEXT_CHARS:
                raise PdfIngestionError("A PDF page exceeds the text extraction limit")
            total_chars += len(text)
            if total_chars > MAX_TOTAL_TEXT_CHARS:
                raise PdfIngestionError("PDF text exceeds the extraction limit")
            extracted.append(text)

        blank_indexes = [index for index, text in enumerate(extracted) if not text]
        ocr_results: dict[int, tuple[str, str]] = {}
        if ocr_enabled and blank_indexes:
            ocr_results = _ocr_scanned_pages(data, blank_indexes)

        pages: list[dict[str, int | str]] = []
        total_chars = 0
        for index, text in enumerate(extracted):
            method = "native" if text else "empty"
            if index in ocr_results:
                text, method = ocr_results[index]
            if len(text) > MAX_PAGE_TEXT_CHARS:
                raise PdfIngestionError("A PDF page exceeds the text extraction limit")
            total_chars += len(text)
            if total_chars > MAX_TOTAL_TEXT_CHARS:
                raise PdfIngestionError("PDF text exceeds the extraction limit")
            pages.append(
                {
                    "page_number": index + 1,
                    "text": text,
                    "extraction_method": method,
                }
            )
        return pages
    except (PdfIngestionError, PdfOcrUnavailableError):
        raise
    except Exception as exc:
        raise PdfIngestionError("PDF could not be parsed") from exc


async def extract_pdf_pages_async(
    data: bytes, *, ocr_enabled: bool = False
) -> list[dict[str, int | str]]:
    """Run CPU-bound PDF parsing/OCR off the API event loop."""
    return await asyncio.to_thread(extract_pdf_pages, data, ocr_enabled=ocr_enabled)
