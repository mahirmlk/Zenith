"""PDF text ingestion stays bounded and produces page-addressable text."""
from io import BytesIO
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pypdf import PdfWriter

from fastapi import HTTPException, Request
from fastapi import UploadFile
from starlette.datastructures import Headers

from routers.projects import list_project_documents, upload_project_pdf
from services import pdf_ingestion
from services.pdf_ingestion import (
    PdfIngestionError,
    PdfOcrUnavailableError,
    extract_pdf_pages,
)


def _blank_pdf(encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    if encrypted:
        writer.encrypt("secret")
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_extracts_one_based_page_records_from_valid_pdf():
    pages = extract_pdf_pages(_blank_pdf())
    assert pages == [{"page_number": 1, "text": "", "extraction_method": "empty"}]


def test_ocr_is_disabled_by_default():
    from config import Settings

    assert Settings().ocr_enabled is False


def test_native_text_is_labeled_without_loading_ocr_runtime(monkeypatch):
    class NativePage:
        def extract_text(self):
            return "native abstract text"

    class NativeReader:
        is_encrypted = False
        pages = [NativePage()]

    monkeypatch.setattr(pdf_ingestion, "PdfReader", lambda *_args, **_kwargs: NativeReader())
    monkeypatch.setattr(
        pdf_ingestion,
        "_ocr_scanned_pages",
        Mock(side_effect=AssertionError("OCR must not run for native text")),
    )

    assert extract_pdf_pages(b"%PDF-native", ocr_enabled=True) == [
        {
            "page_number": 1,
            "text": "native abstract text",
            "extraction_method": "native",
        }
    ]


def test_scanned_and_mixed_pages_report_extraction_method(monkeypatch):
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        is_encrypted = False
        pages = [Page("native words"), Page("")]

    monkeypatch.setattr(pdf_ingestion, "PdfReader", lambda *_args, **_kwargs: Reader())
    monkeypatch.setattr(
        pdf_ingestion,
        "_ocr_scanned_pages",
        lambda _data, indexes: {index: ("recognized scan", "ocr") for index in indexes},
    )

    assert extract_pdf_pages(b"%PDF-mixed", ocr_enabled=True) == [
        {"page_number": 1, "text": "native words", "extraction_method": "native"},
        {"page_number": 2, "text": "recognized scan", "extraction_method": "ocr"},
    ]


def test_ocr_is_disabled_by_default_for_scanned_pages():
    assert extract_pdf_pages(_blank_pdf()) == [
        {"page_number": 1, "text": "", "extraction_method": "empty"}
    ]


def test_missing_tesseract_fails_only_when_a_scanned_page_needs_ocr(monkeypatch):
    class BlankPage:
        def extract_text(self):
            return ""

    class BlankReader:
        is_encrypted = False
        pages = [BlankPage()]

    monkeypatch.setattr(pdf_ingestion, "PdfReader", lambda *_args, **_kwargs: BlankReader())
    fitz = ModuleType("fitz")
    pytesseract = ModuleType("pytesseract")
    pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="tesseract")
    monkeypatch.setitem(sys.modules, "fitz", fitz)
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=object()))
    monkeypatch.setattr(pdf_ingestion.shutil, "which", lambda _command: None)
    assert extract_pdf_pages(b"%PDF-native", ocr_enabled=False) == [
        {"page_number": 1, "text": "", "extraction_method": "empty"}
    ]
    with pytest.raises(PdfOcrUnavailableError, match="Tesseract"):
        pdf_ingestion._ocr_scanned_pages(_blank_pdf(), [0])


def test_ocr_page_cap_marks_remaining_scanned_pages_as_limited(monkeypatch):
    class FakePage:
        rect = SimpleNamespace(width=100, height=100)

        def get_pixmap(self, **_kwargs):
            return SimpleNamespace(width=1, height=1, samples=b"\x00")

    class FakeDocument:
        def __init__(self):
            self.pages = [FakePage() for _ in range(4)]

        def load_page(self, index):
            return self.pages[index]

        def close(self):
            pass

    fitz = ModuleType("fitz")
    fitz.open = lambda **_kwargs: FakeDocument()
    fitz.Matrix = lambda *_args: object()
    fitz.csGRAY = object()
    pytesseract = ModuleType("pytesseract")
    pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="tesseract")
    pytesseract.image_to_string = Mock(return_value="ocr text")
    pil_image = SimpleNamespace(frombytes=lambda *_args: object())
    monkeypatch.setitem(sys.modules, "fitz", fitz)
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=pil_image))
    monkeypatch.setattr(pdf_ingestion.shutil, "which", lambda _command: "tesseract")
    monkeypatch.setattr(pdf_ingestion, "MAX_OCR_PAGES", 2)

    results = pdf_ingestion._ocr_scanned_pages(_blank_pdf(), [0, 1, 2, 3])

    assert results == {
        0: ("ocr text", "ocr"),
        1: ("ocr text", "ocr"),
        2: ("", "ocr_limit"),
        3: ("", "ocr_limit"),
    }
    assert pytesseract.image_to_string.call_count == 2


def test_ocr_page_timeout_is_recorded_as_a_resource_limit(monkeypatch):
    class FakePage:
        rect = SimpleNamespace(width=100, height=100)

        def get_pixmap(self, **_kwargs):
            return SimpleNamespace(width=1, height=1, samples=b"\x00")

    class FakeDocument:
        def load_page(self, _index):
            return FakePage()

        def close(self):
            pass

    fitz = ModuleType("fitz")
    fitz.open = lambda **_kwargs: FakeDocument()
    fitz.Matrix = lambda *_args: object()
    fitz.csGRAY = object()
    pytesseract = ModuleType("pytesseract")
    pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="tesseract")
    pytesseract.image_to_string = Mock(side_effect=RuntimeError("Tesseract process timeout"))
    monkeypatch.setitem(sys.modules, "fitz", fitz)
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=SimpleNamespace(frombytes=lambda *_args: object())))
    monkeypatch.setattr(pdf_ingestion.shutil, "which", lambda _command: "tesseract")

    assert pdf_ingestion._ocr_scanned_pages(_blank_pdf(), [0]) == {0: ("", "ocr_limit")}


def test_ocr_page_pixel_cap_skips_unbounded_page_before_render(monkeypatch):
    class HugePage:
        rect = SimpleNamespace(width=10_000, height=10_000)

        def get_pixmap(self, **_kwargs):
            raise AssertionError("oversized page must not render")

    class FakeDocument:
        def load_page(self, _index):
            return HugePage()

        def close(self):
            pass

    fitz = ModuleType("fitz")
    fitz.open = lambda **_kwargs: FakeDocument()
    fitz.Matrix = lambda *_args: object()
    fitz.csGRAY = object()
    pytesseract = ModuleType("pytesseract")
    pytesseract.pytesseract = SimpleNamespace(tesseract_cmd="tesseract")
    monkeypatch.setitem(sys.modules, "fitz", fitz)
    monkeypatch.setitem(sys.modules, "pytesseract", pytesseract)
    monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=object()))
    monkeypatch.setattr(pdf_ingestion.shutil, "which", lambda _command: "tesseract")

    assert pdf_ingestion._ocr_scanned_pages(_blank_pdf(), [0]) == {0: ("", "ocr_limit")}


def test_project_pdf_upload_returns_503_when_enabled_ocr_runtime_is_missing(monkeypatch):
    from config import Settings

    async def unavailable(*_args, **_kwargs):
        raise PdfOcrUnavailableError("Local Tesseract OCR is unavailable")

    monkeypatch.setattr("config.get_settings", lambda: Settings(ocr_enabled=True))
    monkeypatch.setattr("routers.projects.extract_pdf_pages_async", unavailable)
    upload = UploadFile(
        filename="scan.pdf",
        file=BytesIO(_blank_pdf()),
        headers=Headers({"content-type": "application/pdf"}),
    )

    with pytest.raises(HTTPException) as error:
        import asyncio

        asyncio.run(
            upload_project_pdf(
                "project-1",
                Request({"type": "http", "method": "POST", "path": "/", "headers": []}),
                upload,
                {"user_id": "owner-1"},
                _Database(),
            )
        )

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_project_pdf_upload_closes_temporary_file_when_content_type_is_rejected():
    upload = UploadFile(
        filename="not-a-pdf.txt",
        file=BytesIO(b"not a PDF"),
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(HTTPException) as error:
        await upload_project_pdf(
            "project-1",
            Request({"type": "http", "method": "POST", "path": "/", "headers": []}),
            upload,
            {"user_id": "owner-1"},
            _Database(),
        )

    assert error.value.status_code == 415
    assert upload.file.closed


@pytest.mark.asyncio
async def test_project_pdf_upload_closes_temporary_file_when_read_fails(monkeypatch):
    upload = UploadFile(
        filename="paper.pdf",
        file=BytesIO(_blank_pdf()),
        headers=Headers({"content-type": "application/pdf"}),
    )

    async def fail_read(_size: int = -1) -> bytes:
        raise OSError("temporary upload read failed")

    monkeypatch.setattr(upload, "read", fail_read)
    with pytest.raises(OSError, match="temporary upload read failed"):
        await upload_project_pdf(
            "project-1",
            Request({"type": "http", "method": "POST", "path": "/", "headers": []}),
            upload,
            {"user_id": "owner-1"},
            _Database(),
        )

    assert upload.file.closed


@pytest.mark.parametrize("payload", [b"", b"plain text", b"%PDF-not-a-document"])
def test_rejects_empty_or_malformed_pdf(payload: bytes):
    with pytest.raises(PdfIngestionError):
        extract_pdf_pages(payload)


def test_rejects_password_protected_pdf():
    with pytest.raises(PdfIngestionError, match="Password-protected"):
        extract_pdf_pages(_blank_pdf(encrypted=True))


class _Query:
    def __init__(self, db: "_Database", table: str) -> None:
        self.db = db
        self.table = table
        self.filters: dict[str, str] = {}
        self.single = False

    def select(self, *_args: object) -> "_Query":
        return self

    def eq(self, key: str, value: str) -> "_Query":
        self.filters[key] = value
        return self

    def is_(self, *_args: object) -> "_Query":
        return self

    def maybe_single(self) -> "_Query":
        self.single = True
        return self

    def order(self, *_args: object, **_kwargs: object) -> "_Query":
        return self

    def range(self, *_args: object) -> "_Query":
        return self

    async def execute(self) -> SimpleNamespace:
        if self.table == "project_documents":
            rows = self.db.documents
        elif self.table == "projects":
            rows = [self.db.project]
        else:
            rows = []
        filtered = [row for row in rows if all(row.get(key) == value for key, value in self.filters.items())]
        return SimpleNamespace(data=(filtered[0] if filtered else None) if self.single else filtered)


class _Database:
    def __init__(self) -> None:
        self.project = {"id": "project-1", "owner_id": "owner-1", "deleted_at": None}
        self.documents = [{"id": "doc-1", "project_id": "project-1", "filename": "paper.pdf", "page_count": 8}]

    def table(self, table: str) -> _Query:
        return _Query(self, table)


@pytest.mark.asyncio
async def test_project_document_list_is_persisted_and_project_scoped():
    db = _Database()
    listed = await list_project_documents("project-1", {"user_id": "owner-1"}, db)
    assert listed == db.documents

    with pytest.raises(HTTPException) as error:
        await list_project_documents("project-1", {"user_id": "outsider-1"}, db)
    assert error.value.status_code == 404
