from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.saved_searches as routes
from models.schemas import SavedSearchCreate, SavedSearchUpdate


class Query:
    def __init__(self, data):
        self.data = data
        self.filters = {}
        self.action = "select"
        self.payload = None
        self.single = False

    def select(self, *_):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def is_(self, key, value):
        self.filters[key] = None if value == "null" else value
        return self

    def maybe_single(self):
        self.single = True
        return self

    def range(self, *_):
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def insert(self, payload):
        self.action = "insert"
        self.payload = payload
        return self
    async def execute(self):
        rows = [row for row in self.data if all(row.get(k) == v for k, v in self.filters.items())]
        if self.action == "insert":
            row = {"id": str(uuid4()), **self.payload, "created_at": "2026-11-15T00:00:00Z", "updated_at": "2026-11-15T00:00:00Z"}
            self.data.append(row)
            rows = [row]
        elif self.action == "update":
            for row in rows:
                row.update(self.payload)
        elif self.action == "delete":
            self.data[:] = [row for row in self.data if row not in rows]
            rows = []
        return SimpleNamespace(data=(rows[0] if self.single and rows else (None if self.single else rows)))


class DB:
    def __init__(self):
        self.rows = {"saved_searches": []}
    def table(self, name):
        return Query(self.rows.setdefault(name, []))


def test_saved_search_schema_rejects_trimmed_or_blank_text_and_empty_update():
    with pytest.raises(ValidationError):
        SavedSearchCreate(name=" query ", query="quantum", project_id=None)
    with pytest.raises(ValidationError):
        SavedSearchUpdate()
    with pytest.raises(ValidationError):
        SavedSearchUpdate(query=" ")


@pytest.mark.asyncio
async def test_saved_search_creation_is_owner_scoped_and_run_uses_fresh_idempotency(monkeypatch):
    db = DB()
    user_id = str(uuid4())
    body = SavedSearchCreate(name="Quantum", query="quantum computing", model=None)
    created = await routes.create_saved_search(body, request=None, user={"user_id": user_id}, supabase=db)
    assert str(created.created_by) == user_id
    assert created.project_id is None

    async def fake_search(request, req, *, user, idempotency_key):
        assert req.query == "quantum computing"
        assert user["user_id"] == user_id
        assert idempotency_key.startswith(f"saved-search:{created.id}:")
        return SimpleNamespace(run_id="run-fresh")

    monkeypatch.setattr("routers.search.search", fake_search)
    result = await routes.run_saved_search(
        created.id, request=None, user={"user_id": user_id}, supabase=db
    )
    assert result.run_id == "run-fresh"


@pytest.mark.asyncio
async def test_personal_saved_search_is_hidden_from_other_users():
    db = DB()
    owner_id, other_id = str(uuid4()), str(uuid4())
    saved_id = uuid4()
    db.rows["saved_searches"].append({
        "id": str(saved_id), "created_by": owner_id, "project_id": None,
        "name": "Private", "query": "quantum", "model": None,
    })
    with pytest.raises(HTTPException) as error:
        await routes._load_accessible(db, saved_id, other_id)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_project_member_can_run_and_creator_can_manage_after_role_downgrade(monkeypatch):
    db = DB()
    user_id, project_id = str(uuid4()), str(uuid4())
    saved_id = uuid4()
    db.rows["saved_searches"].append({
        "id": str(saved_id), "created_by": user_id, "project_id": project_id,
        "name": "Shared", "query": "quantum", "model": None,
    })
    calls = []

    async def reader(_db, requested_project_id, requested_user_id):
        assert requested_project_id == project_id
        assert requested_user_id == user_id
        calls.append("read")
        return {"id": project_id}

    async def writer(*_args):
        calls.append("write-denied")
        raise HTTPException(status_code=403, detail="Project is read-only")

    monkeypatch.setattr(routes, "_project_reader", reader)
    monkeypatch.setattr(routes, "_project_writer", writer)
    row = await routes._load_accessible(db, saved_id, user_id)
    assert row["id"] == str(saved_id)
    row = await routes._load_accessible(db, saved_id, user_id, write=True)
    assert row["id"] == str(saved_id)
    assert calls == ["read", "read", "write-denied"]

    async def fake_search(request, req, *, user, idempotency_key):
        assert req.query == "quantum"
        assert user["user_id"] == user_id
        return SimpleNamespace(run_id="run-viewer")

    monkeypatch.setattr("routers.search.search", fake_search)
    result = await routes.run_saved_search(
        saved_id, request=None, user={"user_id": user_id}, supabase=db
    )
    assert result.run_id == "run-viewer"
