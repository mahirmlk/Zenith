"""Bounded daily polling and notification delivery for opted-in paper watches."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from services.crossref_updates import (
    CrossrefLookup,
    CrossrefUpdate,
    lookup_crossref_updates,
    normalize_doi,
)

logger = logging.getLogger(__name__)
MAX_STATUS_WATCHES_PER_RUN = 100
MAX_CROSSREF_CONCURRENCY = 5
RETRY_AFTER = timedelta(hours=6)


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def _priority(update: CrossrefUpdate) -> tuple[int, int]:
    priorities = {
        "retraction": 0,
        "partial_retraction": 1,
        "withdrawal": 2,
        "removal": 3,
        "expression_of_concern": 4,
    }
    return priorities[update.update_type], -(update.updated_at or date.min).toordinal()


def _notification_row(watch: dict[str, Any], paper: dict[str, Any], update: CrossrefUpdate) -> dict[str, Any]:
    paper_id = str(paper["id"])
    notice_identity = f"{paper_id}:{update.update_type}:{update.notice_doi}"
    notice_key = f"crossref:{hashlib.sha256(notice_identity.encode('utf-8')).hexdigest()}"
    label = update.label or update.update_type.replace("_", " ").title()
    deposit_source = update.deposit_source
    if deposit_source == "publisher":
        source_text = "Publisher"
    elif deposit_source == "retraction-watch":
        source_text = "Retraction Watch"
    else:
        source_text = "not identified in the Crossref record"
    date_text = f" ({update.updated_at.isoformat()})" if update.updated_at else ""
    body = (
        f"Crossref metadata records a {label.lower()} update{date_text} for this paper. "
        f"Depositor/source: {source_text}. "
        f"Notice DOI: {update.notice_doi}. Crossref coverage depends on deposited metadata; "
        "a missing record is not evidence that no update exists."
    )
    return {
        "user_id": watch["user_id"],
        "kind": "paper_status",
        "title": f"Publication status update: {str(paper.get('title') or paper_id)[:180]}",
        "body": body[:1000],
        "paper_id": paper_id,
        "notification_key": notice_key[:500],
        "reason_code": "publication_status_update",
        "reason_text": body[:500],
    }


async def poll_crossref_status_watches(
    supabase: Any,
    *,
    now: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> int:
    """Check a bounded batch of due user watches and persist sourced updates.

    Successful empty results record a check time but never claim a negative
    publication status. Provider errors advance only the retry backoff and do
    not overwrite the last verified paper status.
    """
    now = now or datetime.now(timezone.utc)
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    retry_before = (now - RETRY_AFTER).isoformat()
    try:
        response = await (
            supabase.table("paper_status_watches")
            .select("user_id,paper_id,last_attempt_at,created_at")
            .or_(f"last_attempt_at.is.null,last_attempt_at.lt.{retry_before}")
            .order("last_attempt_at", desc=False)
            .order("created_at", desc=False)
            .limit(MAX_STATUS_WATCHES_PER_RUN)
            .execute()
        )
    except Exception:
        logger.exception("Could not load due Crossref status watches")
        return 0

    watches = response.data or []
    if not watches:
        return 0
    paper_ids = list(dict.fromkeys(str(row.get("paper_id") or "") for row in watches if row.get("paper_id")))
    try:
        paper_response = await (
            supabase.table("papers")
            .select("id,title,doi,publication_update_type,publication_update_doi")
            .in_("id", paper_ids)
            .execute()
        )
        papers = {str(row["id"]): row for row in (paper_response.data or []) if row.get("id")}
    except Exception:
        logger.exception("Could not load papers for Crossref status watches")
        return 0

    papers_by_doi: dict[str, list[dict[str, Any]]] = {}
    for paper in papers.values():
        doi = normalize_doi(paper.get("doi"))
        if doi:
            papers_by_doi.setdefault(doi, []).append(paper)

    semaphore = asyncio.Semaphore(MAX_CROSSREF_CONCURRENCY)
    owned_client = client is None
    active_client = client or httpx.AsyncClient(timeout=10.0)

    async def fetch(doi: str) -> tuple[str, CrossrefLookup | Exception]:
        async with semaphore:
            try:
                return doi, await lookup_crossref_updates(doi, client=active_client)
            except Exception as exc:
                return doi, exc

    try:
        lookups = dict(await asyncio.gather(*(fetch(doi) for doi in papers_by_doi))) if papers_by_doi else {}
    finally:
        if owned_client:
            await active_client.aclose()

    notifications: list[dict[str, Any]] = []
    by_paper: dict[str, list[dict[str, Any]]] = {}
    for doi, doi_papers in papers_by_doi.items():
        result = lookups.get(doi)
        if isinstance(result, Exception) or result is None:
            logger.warning("Crossref status lookup failed for DOI %s", doi)
            continue
        checked_at = now.isoformat()
        payload: dict[str, Any] = {"publication_update_checked_at": checked_at}
        if result.updates:
            latest = sorted(result.updates, key=_priority)[0]
            payload.update(
                {
                    "publication_update_type": latest.update_type,
                    "publication_update_doi": latest.notice_doi,
                    "publication_update_label": latest.label,
                    "publication_update_date": latest.updated_at.isoformat() if latest.updated_at else None,
                    "publication_update_source": "crossref",
                    "publication_update_deposit_source": latest.deposit_source,
                }
            )
        for paper in doi_papers:
            try:
                await supabase.table("papers").update(payload).eq("id", paper["id"]).execute()
            except Exception:
                logger.exception("Could not persist Crossref status for paper %s", paper.get("id"))
                continue
            if result.updates:
                by_paper[str(paper["id"])] = [item.model_dump(mode="json") for item in result.updates]

    for watch in watches:
        paper_id = str(watch.get("paper_id") or "")
        paper = papers.get(paper_id)
        try:
            await (
                supabase.table("paper_status_watches")
                .update({"last_attempt_at": now.isoformat()})
                .eq("user_id", watch.get("user_id"))
                .eq("paper_id", paper_id)
                .execute()
            )
        except Exception:
            logger.exception("Could not update Crossref watch retry time")
        if paper is None:
            continue
        for update_data in by_paper.get(paper_id, []):
            update = CrossrefUpdate.model_validate(update_data)
            notifications.append(_notification_row(watch, paper, update))

    if notifications:
        try:
            await (
                supabase.table("notifications")
                .upsert(
                    notifications,
                    on_conflict="user_id,notification_key",
                    ignore_duplicates=True,
                )
                .execute()
            )
        except Exception:
            logger.exception("Could not persist Crossref status notifications")
            return 0
    return len(notifications)
