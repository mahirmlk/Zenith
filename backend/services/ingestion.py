"""Daily paper ingestion pipeline.

Extracted from ``scripts/daily_fetch.py`` so it can be triggered both by the
CLI script and by an authenticated internal HTTP endpoint (for scheduled
runs on Fly machines or GitHub Actions).
"""
import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from models.schemas import AgentStep
from services.spend_meter import BillingContext

logger = logging.getLogger(__name__)

MAX_EMBED_BATCH = 100
MAX_ARXIV_VERSION_POLL = 200
SUMMARY_BATCH_SIZE = 5
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_PROJECT_STOPWORDS = frozenset({
    "about", "after", "against", "also", "among", "because", "been", "being", "between",
    "could", "does", "each", "from", "have", "into", "more", "most", "other", "over",
    "same", "some", "such", "than", "that", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "under", "using", "very", "were", "what", "when",
    "where", "which", "while", "with", "within", "would", "paper", "study", "research",
})


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


def _watchlist_matches(query: str, paper: dict[str, Any]) -> bool:
    normalized_query = " ".join(_TOKEN_RE.findall(query.lower()))
    if not normalized_query:
        return False
    title = str(paper.get("title") or "")
    abstract = str(paper.get("abstract") or "")
    normalized_text = " ".join(_TOKEN_RE.findall(f"{title} {abstract}".lower()))
    terms = set(normalized_query.split())
    if not terms:
        return False
    text_terms = set(normalized_text.split())
    overlap = terms.intersection(text_terms)
    # Require at least two thirds of query terms to match. A lone query term
    # must match exactly in a title or abstract token.
    return len(overlap) == len(terms) if len(terms) == 1 else len(overlap) / len(terms) >= 2 / 3


def _watchlist_reason(target_type: str, query: str, paper: dict[str, Any]) -> tuple[str, str]:
    """Explain the verified match basis without asserting scientific importance."""
    previous_version = paper.get("_version_change_from")
    current_version = paper.get("source_version")
    if target_type == "topic" and previous_version and current_version:
        updated_at = str(paper.get("source_updated_at") or "")[:10]
        date_text = f" on {updated_at}" if updated_at else ""
        return (
            "preprint_version_updated",
            f"arXiv reports this preprint changed from v{previous_version} to v{current_version}{date_text}; "
            "its title or abstract also matches this topic watch.",
        )
    if target_type == "author":
        return "author_relation", "Semantic Scholar returned this paper for the author you follow."
    if target_type == "citation":
        return "citation_relation", "Semantic Scholar reports that this paper cites the work in your citation watch."

    terms = list(dict.fromkeys(_TOKEN_RE.findall(query.casefold())))
    title_terms = set(_TOKEN_RE.findall(str(paper.get("title") or "").casefold()))
    abstract_terms = set(_TOKEN_RE.findall(str(paper.get("abstract") or "").casefold()))
    matched = [term for term in terms if term in title_terms or term in abstract_terms]
    sources = []
    if any(term in title_terms for term in matched):
        sources.append("title")
    if any(term in abstract_terms for term in matched):
        sources.append("abstract")
    shown_terms = ", ".join(matched[:8])
    if len(matched) > 8:
        shown_terms += f", and {len(matched) - 8} more"
    source_text = " and ".join(sources)
    reason = f"Matched {len(matched)}/{len(terms)} topic-watch terms in the paper {source_text}: {shown_terms}."
    return "topic_term_overlap", reason[:500]


def _project_relevance(project_title: str, source_titles: list[str], paper: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return a conservative lexical project relation, never a scientific claim."""
    candidate_text = f"{paper.get('title') or ''} {paper.get('abstract') or ''}"
    candidate_terms = {
        token for token in _TOKEN_RE.findall(candidate_text.casefold())
        if len(token) >= 4 and token not in _PROJECT_STOPWORDS
    }
    if not candidate_terms:
        return None, None

    best: tuple[int, str] | None = None
    for reference in [project_title, *source_titles]:
        reference_terms = {
            token for token in _TOKEN_RE.findall(reference.casefold())
            if len(token) >= 4 and token not in _PROJECT_STOPWORDS
        }
        overlap = candidate_terms.intersection(reference_terms)
        if len(overlap) >= 2 and (best is None or len(overlap) > best[0]):
            best = (len(overlap), reference)
    if best is None:
        return None, None

    shared = sorted(candidate_terms.intersection({
        token for token in _TOKEN_RE.findall(best[1].casefold())
        if len(token) >= 4 and token not in _PROJECT_STOPWORDS
    }))[:5]
    label = best[1].strip()
    if len(label) > 100:
        label = f"{label[:97].rstrip()}..."
    terms = ", ".join(shared)
    return "project_term_overlap", (
        f'The paper shares topic terms ({terms}) with project title/source "{label}". '
        "This is a text-match hint, not an assessment of scientific importance."
    )[:500]


async def _load_project_references(supabase: Any, watch: dict[str, Any]) -> tuple[str, list[str]] | None:
    """Load bounded project text only while the watch owner still has access."""
    project_id = watch.get("project_id")
    user_id = watch.get("user_id")
    if not project_id or not user_id:
        return None
    project_response = await (
        supabase.table("projects").select("id,owner_id,title")
        .eq("id", project_id).is_("deleted_at", "null").maybe_single().execute()
    )
    project = project_response.data
    if not project:
        return None
    if project.get("owner_id") != user_id:
        membership = await (
            supabase.table("project_members").select("user_id")
            .eq("project_id", project_id).eq("user_id", user_id).maybe_single().execute()
        )
        if not membership.data:
            return None
    sources = await (
        supabase.table("project_sources").select("paper_id")
        .eq("project_id", project_id).range(0, 19).execute()
    )
    paper_ids = list(dict.fromkeys(
        str(row["paper_id"]) for row in (sources.data or []) if row.get("paper_id")
    ))
    source_titles: list[str] = []
    if paper_ids:
        papers = await (
            supabase.table("papers").select("id,title")
            .in_("id", paper_ids).execute()
        )
        source_titles = [str(row.get("title") or "")[:300] for row in (papers.data or []) if row.get("title")]
    return str(project.get("title") or "")[:300], source_titles


async def _load_existing_paper_rows(supabase: Any, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch candidate rows and their known preprint versions in bounded batches."""
    candidate_ids = list(dict.fromkeys(str(paper["id"]) for paper in papers if paper.get("id")))
    preprint_ids = list(dict.fromkeys(
        str(paper["preprint_id"]) for paper in papers if paper.get("preprint_id")
    ))
    rows_by_id: dict[str, dict[str, Any]] = {}
    for column, values in (("id", candidate_ids), ("preprint_id", preprint_ids)):
        for offset in range(0, len(values), MAX_EMBED_BATCH):
            batch = values[offset : offset + MAX_EMBED_BATCH]
            response = await (
                supabase.table("papers")
                .select("id,preprint_id,source_version")
                .in_(column, batch)
                .execute()
            )
            for row in response.data or []:
                if row.get("id"):
                    rows_by_id[str(row["id"])] = row
    return list(rows_by_id.values())


def _mark_preprint_version_changes(
    papers: list[dict[str, Any]], existing_rows: list[dict[str, Any]]
) -> None:
    """Mark only version advances over a previously stored arXiv version."""
    latest_existing_versions: dict[str, int] = {}
    for row in existing_rows:
        preprint_id = row.get("preprint_id")
        version = row.get("source_version")
        if preprint_id and isinstance(version, int):
            latest_existing_versions[str(preprint_id)] = max(
                latest_existing_versions.get(str(preprint_id), 0), version
            )
    for paper in papers:
        preprint_id = paper.get("preprint_id")
        version = paper.get("source_version")
        previous_version = latest_existing_versions.get(str(preprint_id)) if preprint_id else None
        if isinstance(version, int) and previous_version and version > previous_version:
            paper["_version_change_from"] = previous_version


async def _notify_watchlists(
    supabase: Any,
    papers: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    sources_complete: bool = True,
    arxiv_updates_complete: bool = True,
    arxiv_updates_oldest_at: datetime | None = None,
) -> int:
    """Deliver idempotent, cadence-aware in-app alerts for recent papers.

    A notification is one row per (user, watchlist, paper). The database
    unique index added in migration 0007 makes retries safe.
    """
    now = now or datetime.now(timezone.utc)
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    notified = 0
    try:
        response = await (
            supabase.table("watchlists")
            .select("id,user_id,query,target_type,target_id,cadence,enabled,last_checked_at,project_id")
            .eq("enabled", True)
            .execute()
        )
    except Exception:
        logger.exception("Could not load enabled watchlists")
        return 0

    for watch in response.data or []:
        query = str(watch.get("query") or "").strip()
        cadence = watch.get("cadence", "daily")
        interval = timedelta(days=7) if cadence == "weekly" else timedelta(days=1)
        last_checked = _as_utc(watch.get("last_checked_at"))
        if last_checked and now - last_checked < interval:
            continue
        since = last_checked or now - interval
        watch_papers = papers
        target_type = watch.get("target_type") or "topic"
        watch_sources_complete = sources_complete if target_type == "topic" else True
        if target_type == "topic" and not arxiv_updates_complete:
            oldest_update = _as_utc(arxiv_updates_oldest_at)
            # The provider result is sorted newest first. Even a capped result
            # covers this watch window when its last record predates `since`.
            if oldest_update is None or oldest_update >= since:
                watch_sources_complete = False
        if target_type in {"author", "citation"}:
            try:
                from services.semantic_scholar import fetch_watch_papers

                watch_papers = await fetch_watch_papers(
                    target_type, str(watch.get("target_id") or ""), since
                )
                # Persist provider-discovered records so notification links open
                # a real paper page. Ignore conflicts to preserve existing rows
                # (including embeddings) from primary ingestion sources.
                provider_rows = [
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "abstract": item.get("abstract", ""),
                        "authors": item.get("authors", []),
                        "url": item.get("url", ""),
                        "published_at": item.get("published_at"),
                    }
                    for item in watch_papers if item.get("id")
                ]
                if provider_rows:
                    await supabase.table("papers").upsert(
                        provider_rows, on_conflict="id", ignore_duplicates=True
                    ).execute()
            except Exception:
                logger.exception("Could not poll provider for watchlist %s", watch.get("id"))
                watch_sources_complete = False
                watch_papers = []
        matches_by_id: dict[str, dict[str, Any]] = {}
        for paper in watch_papers:
            paper_id = str(paper.get("id") or "")
            published = _as_utc(paper.get("source_updated_at") or paper.get("published_at"))
            if not paper_id or published is None or published < since:
                continue
            # Provider watch endpoints already select papers by stable author
            # identity or inbound citation direction. Applying the topic text
            # matcher here would suppress valid results when names/seed titles
            # do not appear in the citing paper's title or abstract.
            if target_type not in {"author", "citation"} and not _watchlist_matches(query, paper):
                continue
            matches_by_id.setdefault(paper_id, paper)
        matches = list(matches_by_id.values())[:5]

        try:
            if matches:
                project_reference: tuple[str, list[str]] | None = None
                if watch.get("project_id"):
                    try:
                        project_reference = await _load_project_references(supabase, watch)
                    except Exception:
                        # Project context is optional; its read failure must not
                        # suppress the independently valid watch notification.
                        logger.exception("Could not load project context for watchlist %s", watch.get("id"))
                rows = []
                for paper in matches:
                    reason_code, reason_text = _watchlist_reason(target_type, query, paper)
                    project_relevance_code, project_relevance_text = (
                        _project_relevance(*project_reference, paper)
                        if project_reference else (None, None)
                    )
                    rows.append({
                        "user_id": watch["user_id"],
                        "watchlist_id": watch["id"],
                        "project_id": watch.get("project_id"),
                        "kind": "watchlist",
                        "title": (
                            f"New arXiv version for {query}"
                            if paper.get("_version_change_from") else f"New paper for {query}"
                        )[:200],
                        "body": str(paper.get("title") or "")[:200],
                        "reason_code": reason_code,
                        "reason_text": reason_text,
                        "project_relevance_code": project_relevance_code,
                        "project_relevance_text": project_relevance_text,
                        "paper_id": paper["id"],
                    })
                await (
                    supabase.table("notifications")
                    .upsert(
                        rows,
                        on_conflict="user_id,watchlist_id,paper_id",
                        ignore_duplicates=True,
                    )
                    .execute()
                )
                notified += len(matches)
                # Email is a separate, opt-in digest channel. Enqueue only
                # after the corresponding in-app notification upsert succeeds.
                from services.notification_email import enqueue_user_digest

                await enqueue_user_digest(supabase, str(watch["user_id"]), now)

            # Do not move the cursor after a partial provider outage. The
            # idempotency index prevents duplicates on the next full run.
            if watch_sources_complete:
                await (
                    supabase.table("watchlists")
                    .update({"last_checked_at": now.isoformat()})
                    .eq("id", watch["id"])
                    .eq("user_id", watch["user_id"])
                    .execute()
                )
        except Exception:
            logger.exception("Could not process watchlist %s", watch.get("id"))
    return notified


async def _noop_callback(step: AgentStep) -> None:
    pass


async def _poll_crossref_status(supabase: Any) -> int:
    """Check opt-in publication-status watches without failing paper ingest."""
    try:
        from services.crossref_monitor import poll_crossref_status_watches

        return await poll_crossref_status_watches(supabase)
    except Exception:
        logger.exception("Crossref publication-status polling failed")
        return 0


async def _poll_benchmark_watches(supabase: Any) -> int:
    """Poll official benchmark watches after daily paper ingestion."""
    try:
        from services.benchmark_monitor import poll_benchmark_watches

        return await poll_benchmark_watches(supabase)
    except Exception:
        logger.exception("Official benchmark monitoring failed")
        return 0


async def run_daily_fetch(
    max_results: int = 200,
    callback: Callable[[AgentStep], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Fetch, embed, store, and summarise newly published papers."""
    from services.arxiv import fetch_latest_papers, fetch_recently_updated_papers
    from services.huggingface import fetch_hf_daily
    from services.embeddings import embed_texts
    from services.retry import async_retry
    from services.supabase_client import get_supabase
    from agents.summary_agent import summary_agent

    cb = callback or _noop_callback
    billing = BillingContext("system", str(uuid.uuid4()), "daily_ingestion")
    supabase = await get_supabase()

    logger.info("Fetching ArXiv papers...")
    arxiv_papers = await fetch_latest_papers(max_results=max_results)
    logger.info("Found %s ArXiv papers", len(arxiv_papers))

    sources_complete = True
    arxiv_updates_complete = True
    arxiv_updates_oldest_at: datetime | None = None
    try:
        updated_arxiv_papers, arxiv_updates_complete = await fetch_recently_updated_papers(
            max_results=MAX_ARXIV_VERSION_POLL
        )
        arxiv_papers.extend(updated_arxiv_papers)
        update_times = [
            parsed for paper in updated_arxiv_papers
            if (parsed := _as_utc(paper.get("source_updated_at"))) is not None
        ]
        arxiv_updates_oldest_at = min(update_times) if update_times else None
        if not arxiv_updates_complete:
            logger.warning("ArXiv version update poll reached its result bound; some topic-watch cursors may pause")
    except Exception as exc:
        logger.warning("ArXiv version update poll failed: %s", exc)
        arxiv_updates_complete = False

    logger.info("Fetching HuggingFace daily papers...")
    try:
        hf_papers = await fetch_hf_daily()
    except Exception as exc:
        logger.warning("HF fetch failed: %s", exc)
        hf_papers = []
        sources_complete = False
    logger.info("Found %s HF papers", len(hf_papers))

    deduped = {p["id"]: p for p in arxiv_papers + hf_papers}
    papers = list(deduped.values())

    existing_rows = await _load_existing_paper_rows(supabase, papers)
    existing_ids = {str(row["id"]) for row in existing_rows if row.get("id")}
    _mark_preprint_version_changes(papers, existing_rows)
    new_papers = [p for p in papers if p["id"] not in existing_ids]
    logger.info("%s new papers to insert", len(new_papers))

    if not new_papers:
        notified = await _notify_watchlists(
            supabase,
            papers,
            sources_complete=sources_complete,
            arxiv_updates_complete=arxiv_updates_complete,
            arxiv_updates_oldest_at=arxiv_updates_oldest_at,
        )
        crossref_alerts = await _poll_crossref_status(supabase)
        benchmark_alerts = await _poll_benchmark_watches(supabase)
        return {
            "fetched": len(papers),
            "inserted": 0,
            "summarised": 0,
            "watchlists_notified": notified,
            "publication_status_alerts": crossref_alerts,
            "benchmark_alerts": benchmark_alerts,
        }

    texts = [f"{p['title']}\n{p['abstract']}" for p in new_papers]
    embeddings: list[list[float] | None] = []
    try:
        embeddings.extend(await embed_texts(texts, context=billing))
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        embeddings = [None] * len(new_papers)

    rows = []
    for p, emb in zip(new_papers, embeddings):
        rows.append({
            "id": p["id"],
            "title": p["title"],
            "abstract": p["abstract"],
            "authors": p.get("authors", []),
            "url": p.get("url", ""),
            "published_at": p.get("published_at"),
            "doi": p.get("doi"),
            "preprint_id": p.get("preprint_id"),
            "source_version": p.get("source_version"),
            "source_updated_at": p.get("source_updated_at"),
            "embedding": emb,
        })

    for i in range(0, len(rows), MAX_EMBED_BATCH):
        batch = rows[i:i + MAX_EMBED_BATCH]

        async def _upsert(b: list[dict[str, Any]] = batch) -> Any:
            return await supabase.table("papers").upsert(b).execute()

        await async_retry(_upsert, max_retries=3, base_delay=1.0)
        logger.info("Inserted batch %s", i // MAX_EMBED_BATCH + 1)

    summarised = 0
    try:
        for i in range(0, len(new_papers), SUMMARY_BATCH_SIZE):
            batch = new_papers[i:i + SUMMARY_BATCH_SIZE]
            paper_dicts = [
                {"id": p["id"], "title": p["title"], "abstract": p["abstract"]}
                for p in batch
            ]
            enriched = await summary_agent(
                paper_dicts,
                cb,
                user_id="system",
                run_id=billing.run_id,
                operation="daily_ingestion_summary",
            )
            for paper in enriched:
                if paper.get("summary_tldr"):
                    summarised += 1
                async def _update(p: dict[str, Any] = paper) -> Any:
                    return await supabase.table("papers").update({
                        "summary_tldr": p.get("summary_tldr"),
                        "difficulty": p.get("difficulty", "intermediate"),
                        "summary_contributions": p.get("summary_contributions"),
                        "summary_status": p.get("summary_status", "unknown"),
                        "summary_fallback_reason": p.get("summary_fallback_reason"),
                    }).eq("id", p["id"]).execute()

                await async_retry(_update, max_retries=3, base_delay=1.0)
            logger.info("Summarised batch %s", i // SUMMARY_BATCH_SIZE + 1)
            if i + SUMMARY_BATCH_SIZE < len(new_papers):
                await asyncio.sleep(2)
    except Exception as exc:
        logger.warning("Summary generation failed: %s", exc)

    notified = await _notify_watchlists(
        supabase,
        papers,
        sources_complete=sources_complete,
        arxiv_updates_complete=arxiv_updates_complete,
        arxiv_updates_oldest_at=arxiv_updates_oldest_at,
    )
    crossref_alerts = await _poll_crossref_status(supabase)
    benchmark_alerts = await _poll_benchmark_watches(supabase)

    return {
        "fetched": len(papers),
        "inserted": len(new_papers),
        "summarised": summarised,
        "watchlists_notified": notified,
        "publication_status_alerts": crossref_alerts,
        "benchmark_alerts": benchmark_alerts,
    }
