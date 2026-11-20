from __future__ import annotations

import json
import re
import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING, cast
from langchain_core.messages import SystemMessage, HumanMessage
from models.schemas import AgentStep
from services.llm_router import AGENT_MODEL_MAP, get_llm
from services.retry import async_retry
from services.spend_meter import (
    BillingContext,
    SpendLimitExceeded,
    SpendMeterError,
    invoke_metered,
)
from config import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

_PROMPT_PATH = Path(__file__).with_name("prompts") / "summary_prompt.txt"
_summary_prompt_cache: str | None = None

# Concurrency limit for LLM calls
_MAX_CONCURRENT_SUMMARIES = 5
_SUMMARY_CALL_TIMEOUT_SECONDS = 30.0

# Delimiters that mark the untrusted paper content in the LLM prompt.
# Everything inside must be treated as data, never as instructions.
_CONTENT_OPEN = "<paper_content>"
_CONTENT_CLOSE = "</paper_content>"


class SummaryOutputError(ValueError):
    """The provider returned a response that fails the summary contract."""


def _decode_json_object(text: str) -> dict[str, Any]:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object from summary model")
    return cast(dict[str, Any], value)


def _get_summary_prompt() -> str:
    global _summary_prompt_cache
    if _summary_prompt_cache is None:
        _summary_prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _summary_prompt_cache


def _wrap_content(paper: dict[str, Any]) -> str:
    """Wrap crawled/untrusted paper text in explicit delimiters.

    Closing tags in the untrusted text are escaped so a malicious
    title/abstract cannot break out of the delimiter (M3).
    """
    title = (paper.get("title", "") or "").replace("</paper_content>", "<\\/paper_content>")
    abstract = (paper.get("abstract", "") or "").replace("</paper_content>", "<\\/paper_content>")
    body = f"Title: {title}\n\nAbstract: {abstract}"
    return f"{_CONTENT_OPEN}\n{body}\n{_CONTENT_CLOSE}"


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM output, handling markdown fences and partial responses."""
    text = text.strip()
    try:
        return _decode_json_object(text)
    except ValueError:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return _decode_json_object(match.group(1))
        except ValueError:
            pass

    match = re.search(r"(\{.*?\})", text, re.DOTALL)
    if match:
        try:
            return _decode_json_object(match.group(1))
        except ValueError:
            pass

    raise ValueError("No valid JSON found in response")


def _apply_fallback(paper: dict[str, Any], reason: str) -> dict[str, Any]:
    """Graceful degradation when summarisation fails or is skipped."""
    abstract = paper.get("abstract", "")
    paper["summary_tldr"] = abstract[:200] + "..." if abstract else ""
    paper["difficulty"] = None
    paper["summary_contributions"] = []
    paper["summary_status"] = "abstract_preview"
    paper["summary_fallback_reason"] = reason
    return paper


def _validated_summary(parsed: dict[str, Any]) -> tuple[str, str, list[str]]:
    tldr = parsed.get("tldr")
    difficulty = parsed.get("difficulty")
    contributions = parsed.get("contributions")
    if (
        not isinstance(tldr, str)
        or not tldr.strip()
        or len(tldr) > 2000
        or difficulty not in {"introductory", "intermediate", "expert"}
        or not isinstance(contributions, list)
        or len(contributions) > 20
        or any(not isinstance(item, str) or not item.strip() or len(item) > 1000 for item in contributions)
    ):
        raise SummaryOutputError("Summary response failed validation")
    return tldr.strip(), difficulty, contributions


async def _summarise_single_paper(
    paper: dict[str, Any],
    llm: BaseChatModel,
    semaphore: asyncio.Semaphore,
    model: str,
    billing: BillingContext,
) -> dict[str, Any]:
    """Summarise a single paper with concurrency control."""
    messages = [
        SystemMessage(content=_get_summary_prompt()),
        HumanMessage(content=_wrap_content(paper)),
    ]

    try:
        async with semaphore:
            response = await async_retry(
                lambda: invoke_metered(
                    llm,
                    messages,
                    model=model,
                    max_output_tokens=4096,
                    context=billing,
                    timeout_seconds=_SUMMARY_CALL_TIMEOUT_SECONDS,
                ),
                max_retries=3,
                base_delay=1.0,
            )
            response_content = response.content if hasattr(response, "content") else response
            content = response_content if isinstance(response_content, str) else str(response_content)
            parsed = _extract_json(content)
            tldr, difficulty, contributions = _validated_summary(parsed)
            paper["summary_tldr"] = tldr
            paper["difficulty"] = difficulty
            paper["summary_contributions"] = contributions
            paper["summary_status"] = "generated"
            paper["summary_fallback_reason"] = None
    except SpendLimitExceeded:
        _apply_fallback(paper, "spend_limit")
    except SpendMeterError:
        _apply_fallback(paper, "billing_unavailable")
    except SummaryOutputError:
        _apply_fallback(paper, "invalid_output")
    except ValueError:
        _apply_fallback(paper, "invalid_output")
    except Exception:
        _apply_fallback(paper, "provider_unavailable")

    return paper


async def summary_agent(
    papers: list[dict[str, Any]],
    callback: Callable[[AgentStep], Awaitable[None]],
    model_override: Optional[str] = None,
    max_summaries: Optional[int] = None,
    user_id: str = "system",
    run_id: str | None = None,
    operation: str = "paper_summary",
) -> list[dict[str, Any]]:
    """Generate AI summaries, capping LLM fan-out to ``max_summaries`` papers.

    Papers beyond the ceiling are given the abstract-preview fallback without
    any LLM call, bounding per-request cost even when a search returns 30-50
    papers or the user selects a pricier model.
    """
    if max_summaries is None:
        max_summaries = get_settings().max_summaries_per_run
    if max_summaries <= 0:
        max_summaries = len(papers)

    model = model_override or AGENT_MODEL_MAP["summary_default"]
    await callback(AgentStep(agent="summary", status="summarising", count=len(papers)))
    try:
        llm = get_llm(agent="summary_default", model_override=model)
    except Exception:
        for paper in papers:
            _apply_fallback(paper, "billing_unavailable")
        await callback(AgentStep(agent="summary", status="complete", count=len(papers)))
        return papers
    billing = BillingContext(subject_id=user_id, run_id=run_id, operation=operation)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SUMMARIES)

    to_summarise = papers[:max_summaries]
    overflow = papers[max_summaries:]

    tasks = [
        _summarise_single_paper(paper, llm, semaphore, model, billing)
        for paper in to_summarise
    ]
    enriched = await asyncio.gather(*tasks)

    for paper in overflow:
        _apply_fallback(paper, "per_run_cap")

    all_enriched = list(enriched) + list(overflow)

    await callback(AgentStep(agent="summary", status="complete", count=len(all_enriched)))
    return all_enriched
