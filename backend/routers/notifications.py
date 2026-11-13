"""In-app notifications and optional consent-based email preferences."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse

from dependencies import get_current_user
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotifyRequest(BaseModel):
    title: str
    body: str | None = None
    paper_id: str | None = None


class EmailPreferencesUpdate(BaseModel):
    email_opt_in: bool
    email_frequency: str = Field(pattern="^(daily|weekly)$")
    timezone: str = Field(min_length=1, max_length=100)


class UnsubscribeRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)


@router.get("/preferences")
async def get_email_preferences(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    del request
    from services.notification_email import get_preferences
    try:
        return await get_preferences(supabase, user["user_id"])
    except Exception:
        logger.exception("Could not read notification email preferences")
        raise HTTPException(status_code=503, detail="Notification preferences unavailable")


@router.put("/preferences")
async def put_email_preferences(
    body: EmailPreferencesUpdate,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    del request
    from services.notification_email import update_preferences
    try:
        return await update_preferences(
            supabase, user["user_id"], opt_in=body.email_opt_in,
            frequency=body.email_frequency, timezone_name=body.timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        reason = str(exc)
        status = 403 if reason == "confirmed_email_required" else 409
        raise HTTPException(status_code=status, detail=reason) from exc
    except RuntimeError as exc:
        if str(exc) == "notification_email_unavailable":
            raise HTTPException(status_code=503, detail="Email notifications are unavailable") from exc
        raise
    except Exception:
        logger.exception("Could not update notification email preferences")
        raise HTTPException(status_code=503, detail="Notification preferences unavailable")


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_landing(request: Request, token: str = Query(min_length=32, max_length=512)) -> HTMLResponse:
    """Human-readable confirmation page; GET itself never changes consent."""
    from html import escape
    del request
    safe_token = escape(token, quote=True)
    return HTMLResponse(
        "<!doctype html><html><head><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Unsubscribe from Zenith</title></head>"
        "<body><main><h1>Unsubscribe from research email</h1><p>Confirm to stop these email updates.</p>"
        f"<form method=\"post\" action=\"/api/notifications/unsubscribe?token={safe_token}\"><button type=\"submit\">Unsubscribe</button></form>"
        "</main></body></html>",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/unsubscribe")
async def unsubscribe_email(
    request: Request,
    token: str | None = Query(default=None, min_length=32, max_length=512),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    """Apply RFC 8058 one-click unsubscribe without disclosing token validity."""
    from services.notification_email import _token_hash
    token = token or request.query_params.get("token")
    if token is None:
        content_type = request.headers.get("content-type", "")
        try:
            if "application/json" in content_type:
                payload = UnsubscribeRequest.model_validate(await request.json())
                token = payload.token
            elif "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                form = await request.form()
                token = UnsubscribeRequest(token=str(form.get("token", ""))).token
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Invalid unsubscribe request") from exc
    if not token:
        raise HTTPException(status_code=422, detail="Unsubscribe token is required")
    try:
        await supabase.rpc("notification_email_unsubscribe", {"p_token_hash": _token_hash(token)}).execute()
    except Exception:
        logger.exception("One-click unsubscribe operation failed")
        raise HTTPException(status_code=503, detail="Unsubscribe could not be processed")
    return {"status": "ok"}


@router.post("/webhooks/resend")
async def resend_webhook(request: Request, supabase: Any = Depends(get_supabase)) -> dict[str, str]:
    from services.notification_email import process_webhook
    raw = await request.body()
    if len(raw) > 65_536:
        raise HTTPException(status_code=413, detail="Webhook payload too large")
    try:
        valid = await process_webhook(supabase, raw, request.headers)
    except Exception:
        logger.exception("Resend webhook processing failed")
        raise HTTPException(status_code=503, detail="Webhook processing failed")
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    return {"status": "ok"}


@router.get("")
async def list_notifications(
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> Any:
    """List caller-owned alerts, including optional linked project context."""
    try:
        resp = await supabase.table("notifications").select("*").eq("user_id", user["user_id"]).order("created_at", desc=True).range(0, 49).execute()
        return resp.data or []
    except Exception:
        logger.exception("list_notifications failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/read")
async def mark_read(
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    """Mark all notifications read (idempotent)."""
    from datetime import datetime, timezone

    try:
        await supabase.table("notifications").update(
            {"read_at": datetime.now(timezone.utc).isoformat()}
        ).eq("user_id", user["user_id"]).is_("read_at", "null").execute()
        return {"status": "ok"}
    except Exception:
        logger.exception("mark_read failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    """Mark one caller-owned notification read without revealing other IDs."""
    from datetime import datetime, timezone

    try:
        await (
            supabase.table("notifications")
            .update({"read_at": datetime.now(timezone.utc).isoformat()})
            .eq("id", notification_id)
            .eq("user_id", user["user_id"])
            .is_("read_at", "null")
            .execute()
        )
        return {"status": "ok"}
    except Exception:
        logger.exception("mark_notification_read failed")
        raise HTTPException(status_code=500, detail="Internal error")
