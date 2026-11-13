"""Pending account deletion locks other authenticated requests."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from dependencies import get_current_user
from config import Settings


class FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, *_args: Any) -> "FakeQuery":
        return self

    def eq(self, *_args: Any) -> "FakeQuery":
        return self

    def in_(self, *_args: Any) -> "FakeQuery":
        return self

    def limit(self, _value: int) -> "FakeQuery":
        return self

    async def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.rows)


class FakeSupabase:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def table(self, _name: str) -> FakeQuery:
        return FakeQuery(self.rows)


def make_request(method: str = "GET", path: str = "/api/papers") -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


@pytest.mark.asyncio
async def test_pending_deletion_blocks_other_authenticated_requests(monkeypatch):
    async def decode(_token: str) -> dict[str, str]:
        return {"sub": "u1", "aud": "authenticated"}

    async def get_supabase() -> FakeSupabase:
        return FakeSupabase([{"id": "job-1", "status": "pending"}])

    monkeypatch.setattr("dependencies._decode_token", decode)
    monkeypatch.setattr("services.supabase_client.get_supabase", get_supabase)
    monkeypatch.setattr(
        "config.get_settings",
        lambda: Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-test-key",
        ),
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    with pytest.raises(HTTPException) as error:
        await get_current_user(make_request(), credentials)

    assert error.value.status_code == 423


@pytest.mark.asyncio
async def test_pending_deletion_allows_idempotent_delete_retry(monkeypatch):
    async def decode(_token: str) -> dict[str, str]:
        return {"sub": "u1", "aud": "authenticated"}

    async def get_supabase() -> FakeSupabase:
        return FakeSupabase([{"id": "job-1", "status": "pending"}])

    monkeypatch.setattr("dependencies._decode_token", decode)
    monkeypatch.setattr("services.supabase_client.get_supabase", get_supabase)
    monkeypatch.setattr(
        "config.get_settings",
        lambda: Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-test-key",
        ),
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    user = await get_current_user(make_request("DELETE", "/api/account"), credentials)

    assert user["user_id"] == "u1"


@pytest.mark.asyncio
async def test_completed_deletion_record_blocks_still_valid_access_token(monkeypatch):
    async def decode(_token: str) -> dict[str, str]:
        return {"sub": "u1", "aud": "authenticated"}

    async def get_supabase() -> FakeSupabase:
        return FakeSupabase([{"id": "job-1", "status": "complete"}])

    monkeypatch.setattr("dependencies._decode_token", decode)
    monkeypatch.setattr("services.supabase_client.get_supabase", get_supabase)
    monkeypatch.setattr(
        "config.get_settings",
        lambda: Settings(
            supabase_url="https://example.supabase.co",
            supabase_service_role_key="service-test-key",
        ),
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")

    with pytest.raises(HTTPException) as error:
        await get_current_user(make_request(), credentials)

    assert error.value.status_code == 423
    with pytest.raises(HTTPException) as retry_error:
        await get_current_user(make_request("DELETE", "/api/account"), credentials)

    assert retry_error.value.status_code == 423
