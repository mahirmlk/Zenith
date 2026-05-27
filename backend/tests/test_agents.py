import pytest
from agents.research_agent import research_agent
from agents.summary_agent import summary_agent, _extract_json
from models.schemas import AgentStep


def test_extract_json_direct():
    text = '{"tldr": "test", "difficulty": "introductory"}'
    result = _extract_json(text)
    assert result["tldr"] == "test"


def test_extract_json_markdown_fence():
    text = '```json\n{"tldr": "test", "difficulty": "intermediate"}\n```'
    result = _extract_json(text)
    assert result["difficulty"] == "intermediate"


def test_extract_json_invalid():
    with pytest.raises(ValueError):
        _extract_json("not json at all")


@pytest.mark.asyncio
async def test_research_agent_runs():
    steps = []

    async def cb(step: AgentStep):
        steps.append(step)

    papers = await research_agent("transformers", cb)
    assert isinstance(papers, list)
    assert any(s.agent == "research" for s in steps)


@pytest.mark.asyncio
async def test_summary_agent_runs():
    steps = []

    async def cb(step: AgentStep):
        steps.append(step)

    papers = [
        {"id": "p1", "title": "Test Paper", "abstract": "This is a test abstract." * 5},
    ]
    enriched = await summary_agent(papers, cb)
    assert len(enriched) == 1
    assert "summary_tldr" in enriched[0]
    assert "difficulty" in enriched[0]
