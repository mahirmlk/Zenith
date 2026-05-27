import json
import re
from pathlib import Path
from typing import Callable, Awaitable, Optional
from langchain_core.messages import SystemMessage, HumanMessage
from models.schemas import AgentStep
from services.llm_router import get_llm
from services.retry import async_retry

_PROMPT_PATH = Path(__file__).with_name("prompts") / "summary_prompt.txt"
_summary_prompt_cache: str | None = None


def _get_summary_prompt() -> str:
    global _summary_prompt_cache
    if _summary_prompt_cache is None:
        _summary_prompt_cache = _PROMPT_PATH.read_text(encoding="utf-8")
    return _summary_prompt_cache


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM output, handling markdown fences and partial responses."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fence
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding any JSON object in the text
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError("No valid JSON found in response")


async def summary_agent(
    papers: list[dict],
    callback: Callable[[AgentStep], Awaitable[None]],
    model_override: Optional[str] = None,
) -> list[dict]:
    llm = get_llm(agent="summary_default", model_override=model_override)
    enriched = []

    for idx, paper in enumerate(papers):
        await callback(AgentStep(agent="summary", status="summarising", paper_id=paper.get("id"), count=idx + 1))

        text = f"Title: {paper.get('title', '')}\n\nAbstract: {paper.get('abstract', '')}"
        messages = [
            SystemMessage(content=_get_summary_prompt()),
            HumanMessage(content=text),
        ]

        try:
            response = await async_retry(lambda: llm.ainvoke(messages), max_retries=3, base_delay=1.0)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = _extract_json(content)
            paper["summary_tldr"] = parsed.get("tldr", "")
            paper["difficulty"] = parsed.get("difficulty", "intermediate")
            paper["summary_contributions"] = parsed.get("contributions", [])
        except Exception:
            paper["summary_tldr"] = paper.get("abstract", "")[:200] + "..."
            paper["difficulty"] = "intermediate"
            paper["summary_contributions"] = []

        enriched.append(paper)

    await callback(AgentStep(agent="summary", status="complete", count=len(enriched)))
    return enriched
