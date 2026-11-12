"""In-app notifications (update.md §12). No email/SMS channels."""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies import get_current_user
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotifyRequest(BaseModel):
    title: str
    body: str | None = None
    paper_id: str | None = None


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
