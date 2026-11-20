"""Project API role enforcement tests using a small fake Supabase client."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers.projects import (
    MemberInvite,
    NoteCreate,
    ProjectUpdate,
    add_member,
    create_note,
    delete_project,
    get_project,
    list_project_members,
    list_projects,
    remove_project_member,
    update_project,
)


class FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table_name = table
        self.filters = {}
        self.action = "select"
        self.payload = None
        self.is_single = False

    def select(self, *_args):
        self.action = "select"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def maybe_single(self):
        self.is_single = True
        return self

    def is_(self, key, value):
        return self

    def in_(self, key, values):
        self.filters[key] = values
        return self

    def update(self, payload):
        self.action = "update"
        self.payload = payload
        return self

    def upsert(self, payload):
        self.action = "upsert"
        self.payload = payload
        return self

    def delete(self):
        self.action = "delete"
        return self

    def order(self, *_args, **_kwargs):
        return self

    async def execute(self):
        if self.table_name == "projects" and self.action == "select":
            if self.is_single:
                data = self.database.project
            else:
                data = self.database.projects
                if "owner_id" in self.filters:
                    data = [p for p in data if p["owner_id"] == self.filters["owner_id"]]
                if "id" in self.filters:
                    data = [p for p in data if p["id"] in self.filters["id"]]
        elif self.table_name == "project_members" and self.action == "upsert":
            match = next((
                row for row in self.database.members
                if row.get("project_id") == self.payload["project_id"]
                and row.get("user_id") == self.payload["user_id"]
            ), None)
            if match:
                match.update(self.payload)
            else:
                self.database.members.append(self.payload)
            data = [self.payload]
        elif self.table_name == "project_members" and self.action == "delete":
            self.database.members[:] = [
                row for row in self.database.members
                if not all(row.get(key) == value for key, value in self.filters.items())
            ]
            data = []
        elif self.table_name == "project_members":
            data = [
                row for row in self.database.members
                if all(row.get(key) == value for key, value in self.filters.items())
            ]
        elif self.table_name == "projects" and self.action == "update":
            data = [self.payload]
        else:
            raise AssertionError((self.table_name, self.action))
        if self.is_single and isinstance(data, list):
            data = data[0] if data else None
        return SimpleNamespace(data=data)


class FakeSupabase:
    def __init__(self, members):
        self.project = {"id": "project-1", "owner_id": "owner-1", "title": "Original"}
        self.projects = [
            self.project,
            {"id": "project-shared", "owner_id": "owner-2", "title": "Shared"},
        ]
        self.members = members

    def table(self, table):
        return FakeQuery(self, table)


@pytest.mark.asyncio
async def test_viewer_cannot_update_project():
    supabase = FakeSupabase([{"project_id": "project-1", "user_id": "viewer-1", "role": "viewer"}])

    with pytest.raises(HTTPException) as error:
        await update_project(
            "project-1", ProjectUpdate(title="Changed"), {"user_id": "viewer-1"}, supabase
        )

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_member_project_list_includes_shared_projects():
    supabase = FakeSupabase([{"user_id": "member-1", "project_id": "project-shared", "role": "viewer"}])

    result = await list_projects({"user_id": "member-1"}, supabase)

    assert [project["id"] for project in result] == ["project-shared"]


@pytest.mark.asyncio
async def test_project_detail_includes_owner_role():
    supabase = FakeSupabase([])

    result = await get_project("project-1", {"user_id": "owner-1"}, supabase)

    assert result["current_role"] == "owner"


@pytest.mark.asyncio
async def test_project_detail_includes_member_role():
    supabase = FakeSupabase([{"user_id": "viewer-1", "project_id": "project-1", "role": "viewer"}])

    result = await get_project("project-1", {"user_id": "viewer-1"}, supabase)

    assert result["current_role"] == "viewer"


@pytest.mark.asyncio
async def test_editor_cannot_update_project_metadata():
    supabase = FakeSupabase([{"project_id": "project-1", "user_id": "editor-1", "role": "editor"}])

    with pytest.raises(HTTPException) as error:
        await update_project(
            "project-1", ProjectUpdate(title="Changed"), {"user_id": "editor-1"}, supabase
        )

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_delete_project():
    supabase = FakeSupabase([{"project_id": "project-1", "user_id": "viewer-1", "role": "viewer"}])

    with pytest.raises(HTTPException) as error:
        await delete_project("project-1", {"user_id": "viewer-1"}, supabase)

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_invite_project_members():
    supabase = FakeSupabase([{"project_id": "project-1", "user_id": "viewer-1", "role": "viewer"}])

    with pytest.raises(HTTPException) as error:
        await add_member(
            "project-1",
            MemberInvite(user_id="00000000-0000-4000-8000-000000000001", role="viewer"),
            {"user_id": "viewer-1"},
            supabase,
        )

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_add_and_list_project_members():
    supabase = FakeSupabase([])
    member_id = "00000000-0000-4000-8000-000000000001"

    created = await add_member(
        "project-1",
        MemberInvite(user_id=member_id, role="editor"),
        {"user_id": "owner-1"},
        supabase,
    )
    roster = await list_project_members("project-1", {"user_id": "owner-1"}, supabase)

    assert created[0]["user_id"] == member_id
    assert roster == [{"project_id": "project-1", "user_id": member_id, "role": "editor"}]


@pytest.mark.asyncio
async def test_only_owner_can_remove_project_member():
    member_id = "00000000-0000-4000-8000-000000000001"
    supabase = FakeSupabase([{"project_id": "project-1", "user_id": member_id, "role": "viewer"}])

    with pytest.raises(HTTPException) as error:
        await remove_project_member(
            "project-1", member_id, {"user_id": member_id}, supabase
        )

    assert error.value.status_code == 403
    assert len(supabase.members) == 1


@pytest.mark.asyncio
async def test_owner_can_remove_member_without_touching_other_projects():
    member_id = "00000000-0000-4000-8000-000000000001"
    supabase = FakeSupabase([
        {"project_id": "project-1", "user_id": member_id, "role": "viewer"},
        {"project_id": "project-shared", "user_id": member_id, "role": "editor"},
    ])

    result = await remove_project_member(
        "project-1", member_id, {"user_id": "owner-1"}, supabase
    )

    assert result == {"status": "ok"}
    assert supabase.members == [{"project_id": "project-shared", "user_id": member_id, "role": "editor"}]


@pytest.mark.asyncio
async def test_owner_cannot_remove_self_from_project():
    owner_id = "00000000-0000-4000-8000-000000000002"
    supabase = FakeSupabase([])
    supabase.project["owner_id"] = owner_id

    with pytest.raises(HTTPException) as error:
        await remove_project_member("project-1", owner_id, {"user_id": owner_id}, supabase)

    assert error.value.status_code == 422


def test_member_invite_rejects_malformed_user_id():
    with pytest.raises(ValidationError):
        MemberInvite(user_id="not-a-uuid", role="viewer")


@pytest.mark.asyncio
async def test_viewer_cannot_add_project_notes():
    supabase = FakeSupabase([{"project_id": "project-1", "user_id": "viewer-1", "role": "viewer"}])

    with pytest.raises(HTTPException) as error:
        await create_note(
            "project-1",
            NoteCreate(content="viewer draft"),
            {"user_id": "viewer-1"},
            supabase,
        )

    assert error.value.status_code == 403
