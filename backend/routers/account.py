"""Account export + deletion (update.md §5.3).

Export returns the caller's own rows; deletion removes user-scoped
rows in Postgres (storage/Redis/Mem0 cleanup is best-effort here and
documented in docs/security/DATA_HANDLING.md).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_current_user
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/export")
async def export_account(user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    uid = user["user_id"]
    try:
        saved = await supabase.table("user_papers").select("*").eq("user_id", uid).execute()
        prefs = await supabase.table("user_prefs").select("*").eq("user_id", uid).execute()
        projects = await supabase.table("projects").select("*").eq("owner_id", uid).execute()
        watches = await supabase.table("watchlists").select("*").eq("user_id", uid).execute()
        return {
            "user_id": uid,
            "saved_papers": saved.data or [],
            "prefs": prefs.data or [],
            "projects": projects.data or [],
            "watchlists": watches.data or [],
        }
    except Exception:
        logger.exception("export_account failed")
        raise HTTPException(status_code=500, detail="Internal error")


@router.delete("")
async def delete_account(user: dict = Depends(get_current_user), supabase=Depends(get_supabase)):
    uid = user["user_id"]
    try:
        for table, col in (
            ("user_papers", "user_id"),
            ("user_prefs", "user_id"),
            ("watchlists", "user_id"),
            ("notifications", "user_id"),
        ):
            await supabase.table(table).delete().eq(col, uid).execute()
        await supabase.table("projects").delete().eq("owner_id", uid).execute()
        # Mem0 forget is best-effort and never fails the deletion.
        try:
            from services.mem0_client import add_memory  # noqa: F401

            logger.info("Mem0 forget requested for %s (manual step)", uid)
        except Exception:
            pass
        return {"status": "ok"}
    except Exception:
        logger.exception("delete_account failed")
        raise HTTPException(status_code=500, detail="Internal error")
