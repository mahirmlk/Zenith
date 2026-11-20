"""Focused invitation API and Auth Admin contract tests."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.project_invitations as routes
import services.project_invitations as invitation_service


class Query:
    def __init__(self, db, table):
        self.db, self.name = db, table
        self.filters, self.gt_filters, self.payload, self.action = {}, {}, None, "select"
        self.single = False

    def select(self, *_):
        self.action = "select"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        self.filters[key] = values
        return self

    def gt(self, key, value):
        self.gt_filters[key] = value
        return self

    def maybe_single(self):
        self.single = True
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, *_):
        return self

    def limit(self, *_):
        return self

    def insert(self, payload):
        self.action, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.action, self.payload = "update", payload
        return self

    async def execute(self):
        rows = self.db.rows.setdefault(self.name, [])
        selected = [
            r
            for r in rows
            if all(
                (r.get(k) in v if isinstance(v, list) else r.get(k) == v)
                for k, v in self.filters.items()
            ) and all(str(r.get(k, "")) > str(v) for k, v in self.gt_filters.items())
        ]
        if self.action == "insert":
            row = {
                "id": str(uuid4()),
                "created_at": datetime.now(timezone.utc).isoformat(),
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


class Admin:
    def __init__(self):
        self.calls, self.error = [], None
        self.user = SimpleNamespace(email="member@example.com", email_confirmed_at="2026-01-01T00:00:00Z")

    async def get_user_by_id(self, _user_id):
        return SimpleNamespace(user=self.user)

    async def invite_user_by_email(self, email, *, options):
        self.calls.append((email, options))
        if self.error:
            raise self.error


class DB:
    def __init__(self):
        self.rows = {
            "projects": [{"id": str(PROJECT), "owner_id": OWNER, "title": "T"}],
            "project_invitations": [],
        }
        self.auth = SimpleNamespace(admin=Admin())
        self.rpc_result = {"status": "accepted", "project_id": str(PROJECT), "role": "viewer"}
        self.rpc_calls = []

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, args):
        self.rpc_calls.append((name, args))
        return SimpleNamespace(execute=lambda: _rpc_result(self.rpc_result))


async def _rpc_result(value):
    return SimpleNamespace(data=value)


PROJECT, OWNER = uuid4(), "owner-1"
OWNER_USER = {"user_id": OWNER, "email": "owner@example.com"}


@pytest.fixture(autouse=True)
def owner_project(monkeypatch):
    async def _owner(_db, project_id, user_id):
        if user_id != OWNER:
            raise HTTPException(403, "denied")
        return {"id": str(project_id), "owner_id": OWNER, "title": "T"}

    monkeypatch.setattr(routes, "_owned_project", _owner)


def test_invalid_email_and_role_rejected():
    with pytest.raises(ValidationError):
        routes.ProjectInvitationCreate(email="bad", role="viewer")
    with pytest.raises(ValidationError):
        routes.ProjectInvitationCreate(email="a@b.com", role="owner")


@pytest.mark.asyncio
async def test_non_owner_cannot_create_invite():
    with pytest.raises(HTTPException) as exc:
        await routes.create_project_invitation(
            PROJECT,
            routes.ProjectInvitationCreate(email="a@example.com", role="viewer"),
            request=None,
            user={"user_id": "member"},
            supabase=DB(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_normalizes_email_and_uses_fixed_auth_callback(monkeypatch):
    monkeypatch.setattr(
        invitation_service,
        "get_settings",
        lambda: SimpleNamespace(app_url="https://app.example", app_env="production"),
    )
    db = DB()
    result = await routes.create_project_invitation(
        PROJECT,
        routes.ProjectInvitationCreate(email="Invitee@Example.com", role="editor"),
        request=None,
        user=OWNER_USER,
        supabase=db,
    )
    assert result["email"] == "invitee@example.com"
    email, options = db.auth.admin.calls[0]
    assert email == "invitee@example.com"
    assert options == {
        "redirect_to": f"https://app.example/projects/invitations/accept?invitation_id={result['id']}"
    }
    assert db.rows["project_invitations"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_active_invitation_for_another_project_is_not_reissued(monkeypatch):
    monkeypatch.setattr(
        invitation_service,
        "get_settings",
        lambda: SimpleNamespace(app_url="https://app.example", app_env="production"),
    )
    db = DB()
    db.rows["project_invitations"].append(
        {
            "id": str(uuid4()),
            "project_id": str(uuid4()),
            "normalized_email": "invitee@example.com",
            "email": "invitee@example.com",
            "role": "viewer",
            "status": "pending",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        }
    )
    with pytest.raises(HTTPException) as exc:
        await routes.create_project_invitation(
            PROJECT,
            routes.ProjectInvitationCreate(email="invitee@example.com", role="editor"),
            request=None,
            user=OWNER_USER,
            supabase=db,
        )
    assert exc.value.status_code == 409
    assert "another project" in exc.value.detail
    assert db.auth.admin.calls == []


def test_production_callback_requires_https(monkeypatch):
    monkeypatch.setattr(
        invitation_service,
        "get_settings",
        lambda: SimpleNamespace(app_url="http://app.example", app_env="production"),
    )
    with pytest.raises(ValueError, match="HTTPS"):
        invitation_service.invitation_redirect_url(uuid4())


@pytest.mark.asyncio
async def test_provider_failure_marks_delivery_failed_and_existing_account_uses_inbox(
    monkeypatch, caplog
):
    monkeypatch.setattr(
        invitation_service,
        "get_settings",
        lambda: SimpleNamespace(app_url="https://app.example", app_env="production"),
    )
    db = DB()
    db.auth.admin.error = RuntimeError("User already registered: private@example.com")
    result = await routes.create_project_invitation(
        PROJECT,
        routes.ProjectInvitationCreate(email="private@example.com", role="viewer"),
        request=None,
        user=OWNER_USER,
        supabase=db,
    )
    assert result["status"] == "pending"
    assert result["email_sent_at"] is None
    public_response = routes.ProjectInvitationResponse.model_validate(result).model_dump()
    assert "email_sent_at" not in public_response
    assert "private@example.com" not in caplog.text
    assert db.rows["project_invitations"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_unclassified_provider_failure_still_marks_invite_failed(monkeypatch):
    monkeypatch.setattr(
        invitation_service,
        "get_settings",
        lambda: SimpleNamespace(app_url="https://app.example", app_env="production"),
    )
    db = DB()
    db.auth.admin.error = RuntimeError("provider unavailable")
    with pytest.raises(HTTPException) as exc:
        await routes.create_project_invitation(
            PROJECT,
            routes.ProjectInvitationCreate(email="private@example.com", role="viewer"),
            request=None,
            user=OWNER_USER,
            supabase=db,
        )
    assert exc.value.status_code == 502
    assert db.rows["project_invitations"][0]["status"] == "delivery_failed"


@pytest.mark.asyncio
async def test_received_inbox_only_returns_verified_email_pending_active_project_invites():
    db = DB()
    now = datetime.now(timezone.utc)
    db.rows["project_invitations"].extend(
        [
            {
                "id": str(uuid4()), "project_id": str(PROJECT),
                "normalized_email": "member@example.com", "status": "pending",
                "role": "editor", "expires_at": (now + timedelta(minutes=30)).isoformat(),
            },
            {
                "id": str(uuid4()), "project_id": str(PROJECT),
                "normalized_email": "other@example.com", "status": "pending",
                "role": "viewer", "expires_at": (now + timedelta(minutes=30)).isoformat(),
            },
            {
                "id": str(uuid4()), "project_id": str(PROJECT),
                "normalized_email": "member@example.com", "status": "pending",
                "role": "viewer", "expires_at": (now - timedelta(minutes=1)).isoformat(),
            },
        ]
    )
    db.rows["projects"].append(
        {"id": str(uuid4()), "owner_id": OWNER, "title": "Deleted", "deleted_at": now.isoformat()}
    )
    deleted_project_id = db.rows["projects"][-1]["id"]
    db.rows["project_invitations"].append(
        {
            "id": str(uuid4()), "project_id": deleted_project_id,
            "normalized_email": "member@example.com", "status": "pending",
            "role": "viewer", "expires_at": (now + timedelta(minutes=30)).isoformat(),
        }
    )

    result = await routes.list_received_project_invitations(
        user={"user_id": "member"}, supabase=db
    )

    assert len(result) == 1
    assert result[0]["project_id"] == str(PROJECT)
    assert result[0]["project_title"] == "T"
    assert result[0]["role"] == "editor"


@pytest.mark.asyncio
async def test_received_inbox_is_empty_without_auth_confirmed_email():
    db = DB()
    db.auth.admin.user.email_confirmed_at = None
    assert await routes.list_received_project_invitations(
        user={"user_id": "member"}, supabase=db
    ) == []


@pytest.mark.asyncio
async def test_duplicate_resend_revoke_and_accept_rpc(monkeypatch):
    monkeypatch.setattr(
        invitation_service,
        "get_settings",
        lambda: SimpleNamespace(app_url="https://app.example", app_env="production"),
    )
    db = DB()
    created = await routes.create_project_invitation(
        PROJECT,
        routes.ProjectInvitationCreate(email="x@example.com", role="viewer"),
        request=None,
        user=OWNER_USER,
        supabase=db,
    )
    with pytest.raises(HTTPException) as duplicate:
        await routes.create_project_invitation(
            PROJECT,
            routes.ProjectInvitationCreate(email="X@example.com", role="viewer"),
            request=None,
            user=OWNER_USER,
            supabase=db,
        )
    assert duplicate.value.status_code == 409

    row = db.rows["project_invitations"][0]
    row["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await routes.resend_project_invitation(
        PROJECT, created["id"], request=None, user=OWNER_USER, supabase=db
    )
    assert len(db.auth.admin.calls) == 2
    assert (
        await routes.revoke_project_invitation(PROJECT, created["id"], user=OWNER_USER, supabase=db)
    )["status"] == "revoked"
    await routes.accept_project_invitation(
        uuid4(), request=None, user={"user_id": "invitee"}, supabase=db
    )
    assert db.rpc_calls[0][0] == "accept_project_invitation"
    assert db.rpc_calls[0][1]["p_accepting_user_id"] == "invitee"


@pytest.mark.asyncio
async def test_acceptance_maps_sql_identity_and_expiry_rejections():
    db = DB()
    for sql_status, http_status in (
        ("email_mismatch", 404),
        ("email_unverified", 404),
        ("expired", 410),
        ("revoked", 410),
    ):
        db.rpc_result = {"status": sql_status}
        with pytest.raises(HTTPException) as exc:
            await routes.accept_project_invitation(
                uuid4(), request=None, user={"user_id": "u"}, supabase=db
            )
        assert exc.value.status_code == http_status


@pytest.mark.asyncio
async def test_acceptance_success_is_idempotent_sql_response():
    db = DB()
    db.rpc_result = {"status": "accepted", "project_id": str(PROJECT), "role": "viewer"}
    assert (
        await routes.accept_project_invitation(
            uuid4(), request=None, user={"user_id": "u"}, supabase=db
        )
    )["status"] == "accepted"
    assert (
        await routes.accept_project_invitation(
            uuid4(), request=None, user={"user_id": "u"}, supabase=db
        )
    )["status"] == "accepted"
