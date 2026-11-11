"""Caller-scoped account export and deletion (update.md §5.3)."""
import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from dependencies import get_current_user
from services import mem0_client
from services.job_queue import remove_runs
from services.run_store import get_run_store
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/account", tags=["account"])


def _rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


async def _run_rows(supabase: Any, user_id: str) -> list[dict[str, Any]]:
    return await _fetch_all(
        lambda: supabase.table("research_runs").select("*").eq("user_id", user_id)
    )


async def _fetch_all(query_factory: Callable[[], Any], page_size: int = 500) -> list[dict[str, Any]]:
    """Read a filtered PostgREST collection past its default response cap."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        result = await query_factory().range(offset, offset + page_size - 1).execute()
        page = _rows(result.data)
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


@router.get("/export")
async def export_account(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, Any]:
    """Export the caller's rows and content in projects they can access."""
    uid = user["user_id"]
    try:
        saved, prefs, owned_projects, member_rows, watches, notifications, runs = await _load_base_data(
            supabase, uid
        )
        owned_project_ids = list(dict.fromkeys(
            str(row["id"]) for row in owned_projects if row.get("id")
        ))
        member_project_ids = list(dict.fromkeys(
            str(row["project_id"])
            for row in member_rows
            if row.get("project_id") and str(row["project_id"]) not in owned_project_ids
        ))
        project_ids = list(dict.fromkeys(owned_project_ids + member_project_ids))
        projects = owned_projects
        if project_ids:
            projects = await _fetch_in_chunks(
                supabase,
                "projects",
                "id",
                project_ids,
            )
            notes = await _project_content_rows(
                supabase, "notes", owned_project_ids, member_project_ids, uid
            )
            sources = await _project_content_rows(
                supabase, "project_sources", owned_project_ids, member_project_ids, uid
            )
        else:
            notes = []
            sources = []

        run_ids = [str(row["id"]) for row in runs if row.get("id")]
        run_events = await _fetch_in_chunks(supabase, "run_events", "run_id", run_ids)

        memories: list[dict[str, Any]] = []
        memory_status = "not configured"
        if mem0_client.is_configured():
            memories = await mem0_client.get_user_profile(uid)
            memory_status = "exported"

        return {
            "user_id": uid,
            "email": user.get("email"),
            "saved_papers": saved,
            "prefs": prefs,
            "projects": projects,
            "project_memberships": member_rows,
            "project_notes": notes,
            "project_sources": sources,
            "watchlists": watches,
            "notifications": notifications,
            "research_runs": runs,
            "run_events": run_events,
            "memories": memories,
            "memory_export_status": memory_status,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("export_account failed")
        raise HTTPException(status_code=500, detail="Internal error")


async def _load_base_data(
    supabase: Any, user_id: str
) -> tuple[list[dict[str, Any]], ...]:
    queries = [
        lambda: supabase.table("user_papers").select("*").eq("user_id", user_id),
        lambda: supabase.table("user_prefs").select("*").eq("user_id", user_id),
        lambda: supabase.table("projects").select("*").eq("owner_id", user_id),
        lambda: supabase.table("project_members").select("*").eq("user_id", user_id),
        lambda: supabase.table("watchlists").select("*").eq("user_id", user_id),
        lambda: supabase.table("notifications").select("*").eq("user_id", user_id),
        lambda: supabase.table("research_runs").select("*").eq("user_id", user_id),
    ]
    results = await asyncio.gather(
        *(_fetch_all(query_factory) for query_factory in queries)
    )
    return tuple(results)


async def _fetch_in_chunks(
    supabase: Any,
    table: str,
    column: str,
    values: list[str],
    *,
    extra_filter: tuple[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset in range(0, len(values), 200):
        chunk = values[offset:offset + 200]

        def query_factory() -> Any:
            query = supabase.table(table).select("*").in_(column, chunk)
            if extra_filter is not None:
                query = query.eq(extra_filter[0], extra_filter[1])
            return query

        rows.extend(await _fetch_all(query_factory))
    return rows


async def _project_content_rows(
    supabase: Any,
    table: str,
    owned_ids: list[str],
    member_ids: list[str],
    user_id: str,
) -> list[dict[str, Any]]:
    # The caller may export all content in projects they own. In shared
    # projects, export only the caller's own authored notes/sources.
    own_content = await _fetch_in_chunks(supabase, table, "project_id", owned_ids)
    member_content = await _fetch_in_chunks(
        supabase,
        table,
        "project_id",
        member_ids,
        extra_filter=("created_by", user_id),
    )
    return own_content + member_content


@router.delete("")
async def delete_account(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    """Delete only the authenticated caller and their stored account data."""
    uid = user["user_id"]
    try:
        runs = await _run_rows(supabase, uid)
        run_ids = [str(row["id"]) for row in runs if row.get("id")]
        run_store = await get_run_store()

        # Make every pending/running run terminal in canonical Postgres before
        # touching leases, checkpoints, or queue entries. Workers that read an
        # older state will fail their atomic try_start/update against this row.
        for row in runs:
            run_id = str(row["id"])
            if row.get("status") in {"pending", "running", "queued"}:
                await (
                    supabase.table("research_runs")
                    .update({"status": "cancelled"})
                    .eq("id", run_id)
                    .eq("user_id", uid)
                    .in_("status", ["pending", "running", "queued"])
                    .execute()
                )
                await run_store.update(run_id, status="cancelled")

        active_ids = [run_id for run_id in run_ids if await run_store.has_active_run(run_id)]
        if active_ids:
            # The caller retries after workers release their leases; do not
            # erase a live checkpoint or remove its run record mid-execution.
            raise HTTPException(
                status_code=409,
                detail="Active research runs were cancelled. Retry account deletion after workers release them.",
            )

        # If Mem0 is configured, failure to remove those records must not be
        # silently reported as complete. Retrying is safe if later cleanup fails.
        if mem0_client.is_configured():
            try:
                await mem0_client.delete_user_memories(uid)
            except Exception as exc:
                logger.exception("Mem0 account cleanup failed")
                raise HTTPException(status_code=502, detail="Account data cleanup is temporarily unavailable") from exc

        from agents.orchestrator import delete_checkpoints_for_runs

        await delete_checkpoints_for_runs(run_ids)
        await remove_runs(set(run_ids))
        for run_id in run_ids:
            await run_store.delete_run(run_id)

        # Delete account-owned rows and records authored by the caller in shared
        # projects before deleting the Auth identity. Auth FK cascades remain a
        # final safety net for any user-scoped rows not listed here.
        if run_ids:
            for offset in range(0, len(run_ids), 200):
                await (
                    supabase.table("run_events")
                    .delete()
                    .in_("run_id", run_ids[offset : offset + 200])
                    .execute()
                )

        for table, column in (
            ("research_runs", "user_id"),
            ("user_papers", "user_id"),
            ("user_prefs", "user_id"),
            ("watchlists", "user_id"),
            ("notifications", "user_id"),
            ("project_members", "user_id"),
            ("notes", "created_by"),
            ("project_sources", "created_by"),
            ("projects", "owner_id"),
        ):
            query = supabase.table(table).delete()
            query = query.eq(column, uid)
            await query.execute()

        # This trusted server-side admin call targets the subject from the
        # verified JWT, never an ID supplied in the request body.
        await supabase.auth.admin.delete_user(uid)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("delete_account failed")
        raise HTTPException(status_code=500, detail="Internal error")
