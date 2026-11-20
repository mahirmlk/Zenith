"""Caller-scoped account export and deletion (update.md §5.3)."""
import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from dependencies import get_current_user
from services import mem0_client
from services.account_deletion import request_account_deletion
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/account", tags=["account"])


def _rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _pick_fields(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Keep internal identifiers and service-only secrets out of portability data."""
    return {field: row[field] for field in fields if field in row}


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
        email_preferences, email_consent_events = await asyncio.gather(
            _fetch_all(
                lambda: supabase.table("notification_email_preferences")
                .select("*")
                .eq("user_id", uid)
            ),
            _fetch_all(
                lambda: supabase.table("notification_email_consent_events")
                .select("*")
                .eq("user_id", uid)
            ),
        )
        personal_searches = await _fetch_all(
            lambda: supabase.table("saved_searches").select("*").eq("created_by", uid).is_("project_id", "null")
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
            annotations = await _project_content_rows(
                supabase, "project_annotations", owned_project_ids, member_project_ids, uid
            )
            project_saved_searches = await _project_content_rows(
                supabase, "saved_searches", owned_project_ids, member_project_ids, uid
            )
            owned_briefs = await _fetch_in_chunks(supabase, "project_briefs", "project_id", owned_project_ids)
            accessible_member_briefs = await _fetch_in_chunks(
                supabase, "project_briefs", "project_id", member_project_ids
            )
            owned_brief_ids = list(dict.fromkeys(
                str(row["id"]) for row in owned_briefs if row.get("id")
            ))
            member_brief_ids = list(dict.fromkeys(
                str(row["id"]) for row in accessible_member_briefs if row.get("id")
            ))
            brief_versions = await _fetch_in_chunks(
                supabase, "project_brief_versions", "brief_id", owned_brief_ids
            )
            brief_versions.extend(await _fetch_in_chunks(
                supabase,
                "project_brief_versions",
                "brief_id",
                member_brief_ids,
                extra_filter=("created_by", uid),
            ))
            project_documents = await _project_content_rows(
                supabase, "project_documents", owned_project_ids, member_project_ids, uid
            )
            document_ids = list(dict.fromkeys(
                str(row["id"]) for row in project_documents if row.get("id")
            ))
            project_document_pages = await _fetch_in_chunks(
                supabase, "project_document_pages", "document_id", document_ids
            )
        else:
            notes = []
            sources = []
            annotations = []
            project_saved_searches = []
            owned_briefs = []
            accessible_member_briefs = []
            brief_versions = []
            project_documents = []
            project_document_pages = []

        paper_ids = list(dict.fromkeys(
            str(row["paper_id"])
            for row in [*saved, *sources]
            if row.get("paper_id")
        ))
        paper_metadata = await _fetch_in_chunks(
            supabase, "papers", "id", paper_ids
        )

        run_ids = [str(row["id"]) for row in runs if row.get("id")]
        run_events = await _fetch_in_chunks(supabase, "run_events", "run_id", run_ids)

        memories: list[dict[str, Any]] = []
        memory_status = "not configured"
        if mem0_client.is_configured():
            memories = await mem0_client.get_user_profile(uid)
            memory_status = "exported"
        elif mem0_client.has_credentials():
            memory_status = "withheld: provider spend limit unconfirmed"

        return {
            "user_id": uid,
            "email": user.get("email"),
            "saved_papers": saved,
            "paper_metadata": paper_metadata,
            "prefs": prefs,
            "projects": projects,
            "project_memberships": member_rows,
            "project_notes": notes,
            "project_sources": sources,
            "project_annotations": annotations,
            "saved_searches": personal_searches + project_saved_searches,
            "project_briefs": owned_briefs + accessible_member_briefs,
            "project_brief_versions": brief_versions,
            "project_documents": project_documents,
            "project_document_pages": project_document_pages,
            "watchlists": watches,
            "notifications": notifications,
            # These tables are service-only. Export the caller's effective
            # email settings and consent history while withholding keyed
            # recipient hashes and delivery-control data.
            "notification_email_preferences": [
                _pick_fields(
                    row,
                    (
                        "email_opt_in",
                        "email_frequency",
                        "timezone",
                        "suppressed",
                        "consented_at",
                        "unsubscribed_at",
                        "updated_at",
                    ),
                )
                for row in email_preferences
            ],
            "notification_email_consent_events": [
                _pick_fields(row, ("action", "source", "created_at"))
                for row in email_consent_events
            ],
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


@router.delete("", status_code=202)
async def delete_account(
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
    supabase: Any = Depends(get_supabase),
) -> dict[str, str]:
    """Persist the caller's deletion intent for resumable background cleanup."""
    del request, supabase  # Dependencies authenticate the caller and verify service access.
    try:
        job_id = await request_account_deletion(user["user_id"])
        return {"status": "accepted", "request_id": job_id}
    except Exception:
        logger.exception("Could not persist account deletion intent")
        raise HTTPException(status_code=503, detail="Account deletion could not be queued; please retry")
