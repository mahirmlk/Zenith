"""PDF text ingestion stays bounded and produces page-addressable text."""
from io import BytesIO

import pytest
from pypdf import PdfWriter
from types import SimpleNamespace

from fastapi import HTTPException

from routers.projects import list_project_documents
from services.pdf_ingestion import PdfIngestionError, extract_pdf_pages


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
    assert pages == [{"page_number": 1, "text": ""}]


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
