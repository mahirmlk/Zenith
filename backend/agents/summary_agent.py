import json
import re
import asyncio
from pathlib import Path
from typing import Callable, Awaitable, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from models.schemas import AgentStep
from services.llm_router import get_llm
from services.retry import async_retry
from config import get_settings

_PROMPT_PATH = Path(__file__).with_name("prompts") / "summary_prompt.txt"
_summary_prompt_cache: str | None = None

# Concurrency limit for LLM calls
_MAX_CONCURRENT_SUMMARIES = 5

# Delimiters that mark the untrusted paper content in the LLM prompt.
# Everything inside must be treated as data, never as instructions.
_CONTENT_OPEN = "<paper_content>"
_CONTENT_CLOSE = "</paper_content>"


def _get_summary_prompt() -> str:
    global _summary_prompt_cache
    if _summary_prompt_cache is None:
        _summary_prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _summary_prompt_cache


def _wrap_content(paper: dict) -> str:
    """Wrap crawled/untrusted paper text in explicit delimiters.

    Closing tags in the untrusted text are escaped so a malicious
    title/abstract cannot break out of the delimiter (M3).
    """
    title = (paper.get("title", "") or "").replace("</paper_content>", "<\\/paper_content>")
    abstract = (paper.get("abstract", "") or "").replace("</paper_content>", "<\\/paper_content>")
    body = f"Title: {title}\n\nAbstract: {abstract}"
    return f"{_CONTENT_OPEN}\n{body}\n{_CONTENT_CLOSE}"


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM output, handling markdown fences and partial responses."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{.*?\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError("No valid JSON found in response")


def _apply_fallback(paper: dict) -> dict:
    """Graceful degradation when summarisation fails or is skipped."""
    abstract = paper.get("abstract", "")
    paper["summary_tldr"] = abstract[:200] + "..." if abstract else ""
    paper["difficulty"] = "intermediate"
    paper["summary_contributions"] = []
    return paper


async def _summarise_single_paper(
    paper: dict,
    llm,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Summarise a single paper with concurrency control."""
    messages = [
        SystemMessage(content=_get_summary_prompt()),
        HumanMessage(content=_wrap_content(paper)),
    ]

    try:
        async with semaphore:
            response = await async_retry(lambda: llm.ainvoke(messages), max_retries=3, base_delay=1.0)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = _extract_json(content)
            paper["summary_tldr"] = parsed.get("tldr", "")
            paper["difficulty"] = parsed.get("difficulty", "intermediate")
            paper["summary_contributions"] = parsed.get("contributions", [])
    except Exception:
        _apply_fallback(paper)

    return paper


async def summary_agent(
    papers: list[dict],
    callback: Callable[[AgentStep], Awaitable[None]],
    model_override: Optional[str] = None,
    max_summaries: Optional[int] = None,
) -> list[dict]:
    """Generate AI summaries, capping LLM fan-out to ``max_summaries`` papers.

    Papers beyond the ceiling are given the abstract-preview fallback without
    any LLM call, bounding per-request cost even when a search returns 30-50
    papers or the user selects a pricier model.
    """
    if max_summaries is None:
        max_summaries = get_settings().max_summaries_per_run
    if max_summaries <= 0:
        max_summaries = len(papers)

    llm = get_llm(agent="summary_default", model_override=model_override)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SUMMARIES)

    await callback(AgentStep(agent="summary", status="summarising", count=len(papers)))

    to_summarise = papers[:max_summaries]
    overflow = papers[max_summaries:]

    tasks = [_summarise_single_paper(paper, llm, semaphore) for paper in to_summarise]
    enriched = await asyncio.gather(*tasks)

    for paper in overflow:
        _apply_fallback(paper)

    all_enriched = list(enriched) + list(overflow)

    await callback(AgentStep(agent="summary", status="complete", count=len(all_enriched)))
    return all_enriched