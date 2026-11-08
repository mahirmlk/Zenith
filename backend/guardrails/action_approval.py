"""Backend-recorded user approvals (update.md §6.4).

An LLM saying "approved" is worthless: approvals are recorded here by
trusted code and checked by the pipeline before high-risk actions.
In-memory for now; the durable implementation belongs in Postgres
(`audit_events` table, migration 0002) before production use.
"""
import time
import uuid
from typing import TypedDict


class Approval(TypedDict):
    user_id: str
    action: str
    resource_id: str
    expires_at: float


_approvals: dict[str, Approval] = {}


def record_approval(user_id: str, action: str, resource_id: str, ttl_seconds: int = 300) -> str:
    token = uuid.uuid4().hex
    _approvals[token] = {
        "user_id": user_id,
        "action": action,
        "resource_id": resource_id,
        "expires_at": time.time() + ttl_seconds,
    }
    return token


def is_approved(token: str | None, user_id: str, action: str, resource_id: str) -> bool:
    if not token:
        return False
    rec = _approvals.get(token)
    if not rec or rec["expires_at"] < time.time():
        return False
    return (
        rec["user_id"] == user_id
        and rec["action"] == action
        and rec["resource_id"] == resource_id
    )
