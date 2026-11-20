from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.project_briefs as routes
from models.schemas import ProjectBriefCreate, ProjectBriefSourceLocator


def test_brief_contract_rejects_bad_spans_and_untrusted_fields():
    source_id = uuid4()
    with pytest.raises(ValidationError):
        ProjectBriefSourceLocator(
            source_type="paper_abstract",
            paper_source_id=source_id,
            start_offset=1,
            end_offset=5,
            quote="short",
        )
    with pytest.raises(ValidationError):
        ProjectBriefCreate(title="Brief", content="text", created_by=uuid4())


def test_rpc_conflicts_map_to_http_409_and_scope_errors_to_403():
    with pytest.raises(HTTPException) as conflict:
        routes._raise_rpc_error(RuntimeError("brief_version_conflict"))
    assert conflict.value.status_code == 409
    with pytest.raises(HTTPException) as denied:
        routes._raise_rpc_error(RuntimeError("project_write_denied"))
    assert denied.value.status_code == 403


class Query:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data
        self.filters: dict[str, object] = {}
        self.single = False

    def select(self, *_args: object) -> "Query":
        return self

    def eq(self, key: str, value: object) -> "Query":
        self.filters[key] = value
        return self

    def maybe_single(self) -> "Query":
        self.single = True
        return self

    async def execute(self) -> SimpleNamespace:
        rows = [row for row in self.data if all(row.get(k) == v for k, v in self.filters.items())]
        return SimpleNamespace(data=rows[0] if self.single and rows else (None if self.single else rows))


class FakeDB:
    def __init__(self) -> None:
        project_id = str(uuid4())
        source_id = str(uuid4())
        self.project_id = project_id
        self.source_id = source_id
        self.tables = {
            "project_sources": [{"id": source_id, "project_id": project_id, "paper_id": "paper-1"}],
            "papers": [{"id": "paper-1", "title": "Paper", "abstract": "alpha βeta gamma"}],
        }

    def table(self, name: str) -> Query:
        return Query(self.tables.get(name, []))


@pytest.mark.asyncio
async def test_source_snapshot_requires_attached_exact_unicode_quote():
    db = FakeDB()
    locator = ProjectBriefSourceLocator(
        source_type="paper_abstract",
        paper_source_id=db.source_id,
        start_offset=6,
        end_offset=10,
        quote="βeta",
    )
    snapshot = await routes._normalize_source_snapshot(db, db.project_id, [locator])
    assert snapshot[0]["quote"] == "βeta"
    assert snapshot[0]["source_id"] == db.source_id
    assert snapshot[0]["paper_id"] == "paper-1"
    assert snapshot[0]["quote_sha256"] == routes.hashlib.sha256("βeta".encode()).hexdigest()

    with pytest.raises(HTTPException) as mismatch:
        await routes._normalize_source_snapshot(
            db,
            db.project_id,
            [locator.model_copy(update={"quote": "beta", "end_offset": 10})],
        )
    assert mismatch.value.status_code == 422

    with pytest.raises(HTTPException) as cross_project:
        await routes._normalize_source_snapshot(db, str(uuid4()), [locator])
    assert cross_project.value.status_code == 422
