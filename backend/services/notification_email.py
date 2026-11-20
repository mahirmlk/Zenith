"""Consent-aware Resend delivery for generic watchlist digest notices."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from config import get_settings
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
POLL_SECONDS = 30
MAX_PER_TICK = 5
MAX_ATTEMPTS = 5  # hard bound on total provider attempts
_worker_task: asyncio.Task[None] | None = None
_worker_id = str(uuid.uuid4())


def delivery_available() -> bool:
    settings = get_settings()
    return bool(
        settings.notifications_email_enabled
        and settings.resend_api_key
        and settings.notifications_from_email
        and settings.resend_webhook_secret
        and settings.notifications_unsubscribe_secret
    )


def _hash(value: str) -> str:
    secret = get_settings().notifications_unsubscribe_secret.encode()
    return hmac.new(secret, value.strip().casefold().encode(), hashlib.sha256).hexdigest()


def _recipient_hashes(email: str) -> list[str]:
    settings = get_settings()
    normalized = _normalize_email(email).encode()
    keys = [settings.notifications_unsubscribe_secret, *settings.notifications_unsubscribe_secret_previous.split(",")]
    return list(dict.fromkeys(
        hmac.new(key.strip().encode(), normalized, hashlib.sha256).hexdigest()
        for key in keys if key.strip()
    ))


def _token_hash(token: str) -> str:
    # The token itself has 256 bits of entropy. A plain one-way digest means
    # already issued links remain valid when the HMAC key is rotated.
    return hashlib.sha256(f"unsubscribe:{token}".encode()).hexdigest()


def _normalize_email(email: str) -> str:
    return parseaddr(email.strip())[1].strip().casefold()


def provider_idempotency_key(outbox_id: str) -> str:
    return f"zenith-watch-digest-{outbox_id}"


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA timezone") from exc
    return value


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


async def confirmed_email(supabase: Any, user_id: str) -> str | None:
    """Read the current confirmed Auth email, never trusting a stale JWT claim."""
    result = await supabase.auth.admin.get_user_by_id(user_id)
    auth_user = getattr(result, "user", None)
    if auth_user is None and isinstance(result, dict):
        auth_user = result.get("user")
    if auth_user is None:
        return None
    email = getattr(auth_user, "email", None) or (auth_user.get("email") if isinstance(auth_user, dict) else None)
    confirmed_at = getattr(auth_user, "email_confirmed_at", None) or (
        auth_user.get("email_confirmed_at") if isinstance(auth_user, dict) else None
    )
    return _normalize_email(str(email)) if email and confirmed_at else None


async def get_preferences(supabase: Any, user_id: str) -> dict[str, Any]:
    result = await supabase.table("notification_email_preferences").select("*").eq("user_id", user_id).maybe_single().execute()
    pref = result.data if isinstance(result.data, dict) else {}
    suppressed = bool(pref.get("suppressed"))
    recipient_hash = pref.get("recipient_hash")
    if recipient_hash and not suppressed:
        rows = await supabase.table("notification_email_suppressions").select("recipient_hash").eq("recipient_hash", recipient_hash).limit(1).execute()
        suppressed = bool(rows.data)
    return {
        "available": delivery_available(),
        "email_opt_in": bool(pref.get("email_opt_in")),
        "email_frequency": pref.get("email_frequency", "daily"),
        "timezone": pref.get("timezone", "UTC"),
        "suppressed": suppressed,
    }


async def update_preferences(supabase: Any, user_id: str, *, opt_in: bool, frequency: str, timezone_name: str) -> dict[str, Any]:
    timezone_name = validate_timezone(timezone_name)
    if opt_in:
        if not delivery_available():
            raise RuntimeError("notification_email_unavailable")
        email = await confirmed_email(supabase, user_id)
        if not email:
            raise PermissionError("confirmed_email_required")
        recipient_hash = _hash(email)
        existing = await supabase.table("notification_email_suppressions").select("recipient_hash").in_("recipient_hash", _recipient_hashes(email)).limit(1).execute()
        if existing.data:
            raise PermissionError("email_suppressed")
    else:
        email = None
        recipient_hash = None
    await supabase.rpc("notification_email_set_preferences", {
        "p_user_id": user_id,
        "p_email_opt_in": bool(opt_in),
        "p_email_frequency": frequency,
        "p_timezone": timezone_name,
        "p_recipient_hash": recipient_hash,
    }).execute()
    return await get_preferences(supabase, user_id)


def next_digest_window(now: datetime, frequency: str, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(validate_timezone(timezone_name))
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    local_now = now.astimezone(zone)
    run_at = local_now.replace(hour=8, minute=0, second=0, microsecond=0)
    if frequency == "weekly":
        run_at += timedelta(days=(7 - run_at.weekday()) % 7)
        if run_at <= local_now:
            run_at += timedelta(days=7)
        width = timedelta(days=7)
    else:
        if run_at <= local_now:
            run_at += timedelta(days=1)
        width = timedelta(days=1)
    window_start_local = run_at - width
    return window_start_local.astimezone(timezone.utc), run_at.astimezone(timezone.utc)


async def enqueue_user_digest(supabase: Any, user_id: str, now: datetime | None = None) -> None:
    if not delivery_available():
        return
    result = await supabase.table("notification_email_preferences").select("email_opt_in,email_frequency,timezone,suppressed,recipient_hash").eq("user_id", user_id).maybe_single().execute()
    pref = result.data if isinstance(result.data, dict) else {}
    if not pref.get("email_opt_in") or pref.get("suppressed"):
        return
    window_start, scheduled_at = next_digest_window(now or datetime.now(timezone.utc), pref.get("email_frequency", "daily"), pref.get("timezone", "UTC"))
    await supabase.table("notification_email_outbox").upsert({
        "user_id": user_id,
        "window_start": window_start.isoformat(),
        "scheduled_at": scheduled_at.isoformat(),
        "frequency": pref.get("email_frequency", "daily"),
        "status": "pending",
        "next_attempt_at": scheduled_at.isoformat(),
    }, on_conflict="user_id,window_start", ignore_duplicates=True).execute()


def verify_svix(raw_body: bytes, headers: Any, secret: str, *, now: int | None = None) -> bool:
    msg_id = headers.get("svix-id", "")
    timestamp = headers.get("svix-timestamp", "")
    signatures = headers.get("svix-signature", "")
    try:
        ts = int(timestamp)
        if not msg_id or abs((now or int(time.time())) - ts) > 300:
            return False
        encoded = secret.removeprefix("whsec_")
        key = base64.b64decode(encoded, validate=True)
        signed = f"{msg_id}.{timestamp}.".encode() + raw_body
        expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        return any(hmac.compare_digest(expected, item.split(",", 1)[-1]) for item in signatures.split() if item.startswith("v1,"))
    except (ValueError, TypeError):
        return False


async def process_webhook(supabase: Any, raw_body: bytes, headers: Any) -> bool:
    settings = get_settings()
    if not settings.resend_webhook_secret or not verify_svix(raw_body, headers, settings.resend_webhook_secret):
        return False
    import json
    try:
        event = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        return False
    if not isinstance(event, dict):
        return False
    event_type = event.get("type")
    if event_type not in {"email.bounced", "email.complained"}:
        return True
    data = event.get("data") or {}
    if not isinstance(data, dict):
        return False
    recipients = data.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]
    if not isinstance(recipients, list) or any(not isinstance(value, str) for value in recipients):
        return False
    event_id = headers.get("svix-id")
    reason = "complaint" if event_type == "email.complained" else "bounce"
    for recipient in recipients[:50]:
        email = _normalize_email(str(recipient))
        if email:
            for recipient_hash in _recipient_hashes(email):
                await supabase.rpc("notification_email_record_suppression", {
                    "p_recipient_hash": recipient_hash, "p_reason": reason,
                    "p_event_id": f"{event_id}:{recipient_hash[:16]}", "p_user_id": None,
                }).execute()
    return True


async def _create_unsubscribe_token(supabase: Any, outbox_id: str, user_id: str) -> str:
    settings = get_settings()
    token = hmac.new(settings.notifications_unsubscribe_secret.encode(), f"outbox:{outbox_id}".encode(), hashlib.sha256).hexdigest()
    await supabase.table("notification_email_unsubscribe_tokens").upsert({
        "token_hash": _token_hash(token), "user_id": user_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
    }, on_conflict="token_hash", ignore_duplicates=True).execute()
    return token


async def _retry(supabase: Any, row: dict[str, Any], error_code: str) -> None:
    attempts = int(row.get("attempts") or 1)
    if attempts >= MAX_ATTEMPTS:
        await supabase.rpc("notification_email_finish", {
            "p_id": row["id"], "p_lease_owner": _worker_id, "p_status": "failed", "p_message_id": None,
        }).execute()
        await supabase.table("notification_email_outbox").update({"last_error_code": error_code}).eq("id", row["id"]).execute()
        return
    delay = min(3600, 30 * (2 ** (attempts - 1)))
    await supabase.table("notification_email_outbox").update({
        "status": "pending", "next_attempt_at": (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(),
        "lease_owner": None, "lease_expires_at": None, "last_error_code": error_code,
    }).eq("id", row["id"]).eq("lease_owner", _worker_id).execute()


async def send_one(supabase: Any, row: dict[str, Any]) -> bool:
    """Recheck user consent and live verified email immediately before delivery."""
    if not delivery_available():
        await supabase.rpc("notification_email_finish", {
            "p_id": row["id"], "p_lease_owner": _worker_id, "p_status": "suppressed", "p_message_id": None,
        }).execute()
        return False
    user_id = str(row["user_id"])
    pref_result = await supabase.table("notification_email_preferences").select("*").eq("user_id", user_id).maybe_single().execute()
    pref = pref_result.data if isinstance(pref_result.data, dict) else {}
    email = await confirmed_email(supabase, user_id)
    if (
        not pref.get("email_opt_in")
        or pref.get("suppressed")
        or not email
        or pref.get("recipient_hash") not in _recipient_hashes(email)
    ):
        await supabase.rpc("notification_email_finish", {
            "p_id": row["id"], "p_lease_owner": _worker_id, "p_status": "suppressed", "p_message_id": None,
        }).execute()
        return False
    suppression = await supabase.table("notification_email_suppressions").select("recipient_hash").in_("recipient_hash", _recipient_hashes(email)).limit(1).execute()
    if suppression.data:
        await supabase.rpc("notification_email_finish", {
            "p_id": row["id"], "p_lease_owner": _worker_id, "p_status": "suppressed", "p_message_id": None,
        }).execute()
        return False
    count_result = await supabase.table("notifications").select("id", count="exact").eq("user_id", user_id).gte("created_at", row["window_start"]).lt("created_at", row["scheduled_at"]).execute()
    count = int(getattr(count_result, "count", None) or len(count_result.data or []))
    if count < 1:
        await supabase.rpc("notification_email_finish", {
            "p_id": row["id"], "p_lease_owner": _worker_id, "p_status": "suppressed", "p_message_id": None,
        }).execute()
        return False
    token = await _create_unsubscribe_token(supabase, str(row["id"]), user_id)
    settings = get_settings()
    app_url = settings.app_url.rstrip("/")
    unsubscribe_url = f"{settings.next_public_api_url.rstrip('/')}/api/notifications/unsubscribe"
    payload = {
        "from": settings.notifications_from_email,
        "to": [email],
        "subject": "Your Zenith research updates",
        "text": f"You have {count} new watchlist research update(s).\n\nOpen Zenith: {app_url}/notifications\n\nUnsubscribe: {unsubscribe_url}?token={token}",
        "headers": {
            "List-Unsubscribe": f"<{unsubscribe_url}?token={token}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }
    # Consent/suppression checked directly before network dispatch above. Idempotency
    # protects a timed-out provider request from generating a duplicate message.
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post("https://api.resend.com/emails", json=payload, headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Idempotency-Key": provider_idempotency_key(str(row["id"])),
            })
        response.raise_for_status()
        result = response.json()
        await supabase.rpc("notification_email_finish", {
            "p_id": row["id"], "p_lease_owner": _worker_id, "p_status": "sent", "p_message_id": result.get("id"),
        }).execute()
        return True
    except Exception as exc:
        logger.warning("Notification email attempt failed (error_class=%s)", type(exc).__name__)
        await _retry(supabase, row, type(exc).__name__[:80])
        return False


async def process_due_batch(supabase: Any | None = None) -> int:
    if not delivery_available():
        return 0
    client = supabase or await get_supabase()
    result = await client.rpc("notification_email_claim", {"p_lease_owner": _worker_id, "p_limit": MAX_PER_TICK}).execute()
    rows = _rows(result.data)
    for row in rows:
        try:
            await send_one(client, row)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Notification email job failed (error_class=%s)", type(exc).__name__)
            await _retry(client, row, type(exc).__name__[:80])
    return len(rows)


async def worker_loop() -> None:
    while True:
        try:
            await process_due_batch()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Notification email worker poll failed (error_class=%s)", type(exc).__name__)
        await asyncio.sleep(POLL_SECONDS)


def start_worker() -> asyncio.Task[None] | None:
    global _worker_task
    if not delivery_available():
        logger.info("Notification email delivery disabled or incompletely configured")
        return None
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(worker_loop())
    return _worker_task


async def stop_worker() -> None:
    global _worker_task
    task, _worker_task = _worker_task, None
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
