"""Durable, resumable account deletion worker.

The user-facing route records an intent and returns immediately. A service-only
Postgres lease coordinates workers across API replicas; each external cleanup
step is idempotent and recorded only after it succeeds.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from services import mem0_client
from services.job_queue import remove_runs
from services.run_store import get_run_store
from services.supabase_client import get_supabase

logger = logging.getLogger(__name__)
_worker_task: asyncio.Task[None] | None = None
_WORKER_ID = str(uuid.uuid4())
_POLL_SECONDS = 5
_LEASE_SECONDS = 600
_PRUNE_INTERVAL_SECONDS = 86_400


def _rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


async def request_account_deletion(user_id: str) -> str:
    """Persist or reuse the caller's active deletion job."""
    supabase = await get_supabase()
    result = await supabase.rpc(
        "request_account_deletion", {"p_user_id": user_id}
    ).execute()
    value = result.data
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("request_account_deletion") or value.get("id")
    if not value:
        raise RuntimeError("Deletion intent was not persisted")
    return str(value)


async def _rpc_bool(supabase: Any, name: str, params: dict[str, Any]) -> bool:
    response = await supabase.rpc(name, params).execute()
    return response.data is True


async def _mark_step(supabase: Any, job_id: str, step: str) -> None:
    updated = await _rpc_bool(
        supabase,
        "complete_account_deletion_step",
        {"p_job_id": job_id, "p_lease_owner": _WORKER_ID, "p_step": step},
    )
    if not updated:
        raise RuntimeError("deletion_lease_lost")


async def _delete_rows(supabase: Any, job: dict[str, Any]) -> None:
    user_id = str(job["user_id"])
    steps = set(job.get("completed_steps") or [])
    run_ids = [str(value) for value in (job.get("run_ids") or [])]
    run_store = await get_run_store()

    if "cancel_runs" not in steps:
        for run_id in run_ids:
            await (
                supabase.table("research_runs")
                .update({"status": "cancelled"})
                .eq("id", run_id)
                .eq("user_id", user_id)
                .in_("status", ["pending", "running", "queued"])
                .execute()
            )
            await run_store.update(run_id, status="cancelled")
        await _mark_step(supabase, str(job["id"]), "cancel_runs")
        steps.add("cancel_runs")

    active_ids = [run_id for run_id in run_ids if await run_store.has_active_run(run_id)]
    if active_ids:
        await _release_job(supabase, job, "active_run_lease", 20)
        return

    current_step = "memories"
    try:
        if current_step not in steps:
            if mem0_client.is_configured():
                await mem0_client.delete_user_memories(user_id)
            await _mark_step(supabase, str(job["id"]), current_step)
            steps.add(current_step)

        current_step = "checkpoints"
        if current_step not in steps:
            from agents.orchestrator import delete_checkpoints_for_runs

            await delete_checkpoints_for_runs(run_ids)
            await _mark_step(supabase, str(job["id"]), current_step)
            steps.add(current_step)

        current_step = "queue"
        if current_step not in steps:
            await remove_runs(set(run_ids))
            await _mark_step(supabase, str(job["id"]), current_step)
            steps.add(current_step)

        current_step = "run_store"
        if current_step not in steps:
            for run_id in run_ids:
                await run_store.delete_run(run_id)
            await _mark_step(supabase, str(job["id"]), current_step)
            steps.add(current_step)

        current_step = "run_events"
        if current_step not in steps:
            for offset in range(0, len(run_ids), 200):
                await (
                    supabase.table("run_events")
                    .delete()
                    .in_("run_id", run_ids[offset : offset + 200])
                    .execute()
                )
            await _mark_step(supabase, str(job["id"]), current_step)
            steps.add(current_step)

        current_step = "user_rows"
        if current_step not in steps:
            for table, column in (
                ("research_runs", "user_id"),
                ("user_papers", "user_id"),
                ("user_prefs", "user_id"),
                ("watchlists", "user_id"),
                ("notifications", "user_id"),
                ("project_members", "user_id"),
                ("notes", "created_by"),
                ("project_sources", "created_by"),
                ("project_documents", "created_by"),
                ("projects", "owner_id"),
            ):
                await supabase.table(table).delete().eq(column, user_id).execute()
            await _mark_step(supabase, str(job["id"]), current_step)
            steps.add(current_step)

        current_step = "auth_user"
        if current_step not in steps:
            try:
                await supabase.auth.admin.delete_user(user_id)
            except Exception as exc:
                status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
                code = str(getattr(exc, "code", "")).casefold()
                if status != 404 and code not in {"user_not_found", "user_not_found_error"}:
                    raise
            await _mark_step(supabase, str(job["id"]), current_step)

        finished = await _rpc_bool(
            supabase,
            "finish_account_deletion_job",
            {"p_job_id": str(job["id"]), "p_lease_owner": _WORKER_ID},
        )
        if not finished:
            raise RuntimeError("deletion_lease_lost")
    except asyncio.CancelledError:
        await asyncio.shield(_release_job(supabase, job, current_step, 5))
        raise
    except Exception as exc:
        logger.error(
            "Account deletion step failed (step=%s, error_class=%s)",
            current_step,
            type(exc).__name__,
        )
        attempt = int(job.get("attempts") or 1)
        delay = min(3600, 30 * (2 ** min(max(attempt - 1, 0), 7)))
        await _release_job(supabase, job, current_step, delay)


async def _release_job(
    supabase: Any, job: dict[str, Any], error_code: str, delay_seconds: int
) -> None:
    await supabase.rpc(
        "release_account_deletion_job",
        {
            "p_job_id": str(job["id"]),
            "p_lease_owner": _WORKER_ID,
            "p_error_code": error_code,
            "p_delay_seconds": delay_seconds,
        },
    ).execute()


async def process_one_account_deletion() -> bool:
    """Claim and process one durable job, returning whether one was claimed."""
    supabase = await get_supabase()
    result = await supabase.rpc(
        "claim_account_deletion_job",
        {"p_lease_owner": _WORKER_ID, "p_lease_seconds": _LEASE_SECONDS},
    ).execute()
    rows = _rows(result.data)
    if not rows:
        return False
    await _delete_rows(supabase, rows[0])
    return True


async def account_deletion_worker() -> None:
    """Recover pending jobs after process restarts and retry transient failures."""
    next_prune_at = 0.0
    while True:
        try:
            loop = asyncio.get_running_loop()
            if loop.time() >= next_prune_at:
                next_prune_at = loop.time() + _PRUNE_INTERVAL_SECONDS
                supabase = await get_supabase()
                await supabase.rpc("prune_account_deletion_jobs", {}).execute()
            claimed = await process_one_account_deletion()
            if not claimed:
                await asyncio.sleep(_POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # The durable row remains pending or lease-expiring and will be
            # claimed again; never log a raw user row or provider response.
            logger.error("Account deletion worker poll failed (error_class=%s)", type(exc).__name__)
            await asyncio.sleep(_POLL_SECONDS)


def start_account_deletion_worker() -> asyncio.Task[None]:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(account_deletion_worker())
        logger.info("Account deletion worker started")
    return _worker_task


async def stop_account_deletion_worker() -> None:
    global _worker_task
    task = _worker_task
    _worker_task = None
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
