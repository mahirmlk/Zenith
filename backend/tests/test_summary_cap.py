import pytest
from agents.summary_agent import summary_agent as summary_agent_func
from agents import summary_agent as summary_agent_module
from models.schemas import AgentStep


class _FakeLLM:
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        return type("R", (), {"content": '{"tldr": "real summary", "difficulty": "expert", "contributions": ["c"]}'})()


def _papers(n):
    return [
        {"id": f"p{i}", "title": f"Paper {i}", "abstract": f"Abstract content {i} " * 20}
        for i in range(n)
    ]


async def _cb(step: AgentStep):
    pass


@pytest.mark.asyncio
async def test_summary_cap_limits_llm_calls(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)

    papers = _papers(5)
    enriched = await summary_agent_func(papers, _cb, max_summaries=2)

    assert len(enriched) == 5
    assert fake.calls == 2
    assert enriched[0]["summary_tldr"] == "real summary"
    assert enriched[2]["summary_tldr"]  # overflow uses abstract fallback
    assert enriched[2]["difficulty"] == "intermediate"


@pytest.mark.asyncio
async def test_summary_no_cap_calls_all(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)

    papers = _papers(3)
    enriched = await summary_agent_func(papers, _cb, max_summaries=10)
    assert len(enriched) == 3
    assert fake.calls == 3


@pytest.mark.asyncio
async def test_summary_content_is_delimited(monkeypatch):
    fake = _FakeLLM()
    captured = {}
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)

    async def tracking_ainvoke(messages):
        captured["human"] = messages[1].content
        return type("R", (), {"content": '{"tldr": "x", "difficulty": "intermediate", "contributions": []}'})()

    fake.ainvoke = tracking_ainvoke
    await summary_agent_func(_papers(1), _cb, max_summaries=1)

    assert captured["human"].startswith("<paper_content>")
    assert captured["human"].endswith("</paper_content>")