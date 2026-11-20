"""Focused source-integrity tests for project annotation API behavior."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.projects as routes
from models.schemas import ProjectAnnotationCreate, ProjectAnnotationUpdate


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters, self.payload, self.action, self.single = {}, None, "select", False

    def select(self, *_):
        self.action = "select"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def maybe_single(self):
        self.single = True
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_args):
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    async def execute(self):
        rows = self.db.rows.setdefault(self.name, [])
        selected = [row for row in rows if all(row.get(key) == value for key, value in self.filters.items())]
        if self.action == "insert":
            row = {
                "id": str(uuid4()),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **self.payload,
            }
            rows.append(row)
            data = [row]
        elif self.action == "update":
            for row in selected:
                row.update(self.payload)
            data = selected
        else:
            data = selected
        if self.single:
            data = data[0] if data else None
        return SimpleNamespace(data=data)


class DB:
    def __init__(self):
        self.rows = {
            "project_sources": [{"id": str(SOURCE_ID), "project_id": str(PROJECT_ID), "paper_id": PAPER_ID}],
            "papers": [{"id": PAPER_ID, "title": "Paper", "abstract": "alpha βeta gamma"}],
            "project_annotations": [],
        }

    def table(self, name):
        return Query(self, name)


PROJECT_ID, SOURCE_ID = uuid4(), uuid4()
PAPER_ID, OWNER_ID = "paper-1", str(uuid4())


@pytest.fixture(autouse=True)
def writable_project(monkeypatch):
    async def _writable(_db, project_id, user_id):
        if user_id != OWNER_ID:
            raise HTTPException(403, "Project is read-only")
        return {"id": str(project_id), "owner_id": OWNER_ID}

    async def _owner(_db, project_id, user_id):
        if user_id not in {OWNER_ID, "viewer-1"}:
            raise HTTPException(404, "Project not found")
        return {"id": str(project_id), "owner_id": OWNER_ID}

    monkeypatch.setattr(routes, "_writable_project", _writable)
    monkeypatch.setattr(routes, "_owned_project", _owner)


def create_payload(**overrides):
    payload = dict(
        source_type="paper_abstract",
        paper_source_id=SOURCE_ID,
        start_offset=6,
        end_offset=10,
        quote="βeta",
        content="Useful result",
    )
    payload.update(overrides)
    return ProjectAnnotationCreate(**payload)


@pytest.mark.asyncio
async def test_create_annotation_checks_exact_unicode_source_slice_and_hash():
    db = DB()
    result = await routes.create_project_annotation(
        str(PROJECT_ID), create_payload(), request=None, user={"user_id": OWNER_ID}, supabase=db
    )

    assert result.quote == "βeta"
    assert result.is_stale is False
    assert result.source_label == "Paper"
    assert db.rows["project_annotations"][0]["quote_sha256"] == routes.hashlib.sha256("βeta".encode()).hexdigest()


@pytest.mark.asyncio
async def test_create_annotation_rejects_quote_that_does_not_match_source():
    with pytest.raises(HTTPException) as error:
        await routes.create_project_annotation(
            str(PROJECT_ID),
            create_payload(quote="beta"),
            request=None,
            user={"user_id": OWNER_ID},
            supabase=DB(),
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_patch_annotation_changes_content_without_changing_anchor():
    db = DB()
    created = await routes.create_project_annotation(
        str(PROJECT_ID), create_payload(), request=None, user={"user_id": OWNER_ID}, supabase=db
    )
    original = dict(db.rows["project_annotations"][0])
    updated = await routes.update_project_annotation(
        str(PROJECT_ID),
        created.id,
        ProjectAnnotationUpdate(content="Updated observation"),
        request=None,
        user={"user_id": OWNER_ID},
        supabase=db,
    )

    assert updated.content == "Updated observation"
    for field in ("paper_source_id", "start_offset", "end_offset", "quote", "quote_sha256"):
        value = getattr(updated, field)
        if field == "paper_source_id":
            value = str(value)
        assert value == original[field]


def test_create_schema_requires_exactly_one_valid_anchor():
    with pytest.raises(ValidationError):
        create_payload(document_id=uuid4())
    with pytest.raises(ValidationError):
        create_payload(created_by=uuid4())
    with pytest.raises(ValidationError):
        ProjectAnnotationUpdate(content="updated", quote="anchor")
