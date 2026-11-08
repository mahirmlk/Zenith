"""Project API role enforcement tests using a small fake Supabase client."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers.projects import MemberInvite, NoteCreate, ProjectUpdate, add_member, create_note, delete_project, list_projects, update_project


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
        elif self.table_name == "project_members":
            data = self.database.members
        elif self.table_name == "projects" and self.action == "update":
            data = [self.payload]
        else:
            raise AssertionError((self.table_name, self.action))
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
    supabase = FakeSupabase([{"user_id": "viewer-1", "role": "viewer"}])

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
async def test_editor_can_update_project():
    supabase = FakeSupabase([{"user_id": "editor-1", "role": "editor"}])

    result = await update_project(
        "project-1", ProjectUpdate(title="Changed"), {"user_id": "editor-1"}, supabase
    )

    assert result == [{"title": "Changed"}]


@pytest.mark.asyncio
async def test_viewer_cannot_delete_project():
    supabase = FakeSupabase([{"user_id": "viewer-1", "role": "viewer"}])

    with pytest.raises(HTTPException) as error:
        await delete_project("project-1", {"user_id": "viewer-1"}, supabase)

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_invite_project_members():
    supabase = FakeSupabase([{"user_id": "viewer-1", "role": "viewer"}])

    with pytest.raises(HTTPException) as error:
        await add_member(
            "project-1",
            MemberInvite(user_id="invitee", role="viewer"),
            {"user_id": "viewer-1"},
            supabase,
        )

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_add_project_notes():
    supabase = FakeSupabase([{"user_id": "viewer-1", "role": "viewer"}])

    with pytest.raises(HTTPException) as error:
        await create_note(
            "project-1",
            NoteCreate(content="viewer draft"),
            {"user_id": "viewer-1"},
            supabase,
        )

    assert error.value.status_code == 403
