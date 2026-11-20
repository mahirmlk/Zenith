import pytest
from agents.summary_agent import summary_agent as summary_agent_func
from agents import summary_agent as summary_agent_module
from models.schemas import AgentStep
from services.spend_meter import SpendLimitExceeded, SpendMeterError


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


async def _invoke_without_meter(llm, messages, **_kwargs):
    return await llm.ainvoke(messages)


@pytest.mark.asyncio
async def test_summary_cap_limits_llm_calls(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)
    monkeypatch.setattr(summary_agent_module, "invoke_metered", _invoke_without_meter)

    papers = _papers(5)
    enriched = await summary_agent_func(papers, _cb, max_summaries=2)

    assert len(enriched) == 5
    assert fake.calls == 2
    assert enriched[0]["summary_tldr"] == "real summary"
    assert enriched[0]["summary_status"] == "generated"
    assert enriched[0]["summary_fallback_reason"] is None
    assert enriched[2]["summary_tldr"]  # overflow uses abstract fallback
    assert enriched[2]["summary_status"] == "abstract_preview"
    assert enriched[2]["summary_fallback_reason"] == "per_run_cap"
    assert enriched[2]["difficulty"] is None


@pytest.mark.asyncio
async def test_summary_no_cap_calls_all(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)
    monkeypatch.setattr(summary_agent_module, "invoke_metered", _invoke_without_meter)

    papers = _papers(3)
    enriched = await summary_agent_func(papers, _cb, max_summaries=10)
    assert len(enriched) == 3
    assert fake.calls == 3


@pytest.mark.asyncio
async def test_summary_content_is_delimited(monkeypatch):
    fake = _FakeLLM()
    captured = {}
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)
    monkeypatch.setattr(summary_agent_module, "invoke_metered", _invoke_without_meter)

    async def tracking_ainvoke(messages):
        captured["human"] = messages[1].content
        return type("R", (), {"content": '{"tldr": "x", "difficulty": "intermediate", "contributions": []}'})()

    fake.ainvoke = tracking_ainvoke
    await summary_agent_func(_papers(1), _cb, max_summaries=1)

    assert captured["human"].startswith("<paper_content>")
    assert captured["human"].endswith("</paper_content>")


@pytest.mark.asyncio
async def test_summary_provider_attempt_has_bounded_application_timeout(monkeypatch):
    fake = _FakeLLM()
    captured: dict[str, object] = {}
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)

    async def capture_timeout(_llm, _messages, **kwargs):
        captured.update(kwargs)
        return type("R", (), {"content": '{"tldr": "summary", "difficulty": "expert", "contributions": []}'})()

    monkeypatch.setattr(summary_agent_module, "invoke_metered", capture_timeout)
    result = await summary_agent_func(_papers(1), _cb, max_summaries=1)

    assert result[0]["summary_status"] == "generated"
    assert captured["timeout_seconds"] == summary_agent_module._SUMMARY_CALL_TIMEOUT_SECONDS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    [
        (SpendLimitExceeded("limit"), "spend_limit"),
        (SpendMeterError("ledger unavailable"), "billing_unavailable"),
        (RuntimeError("provider failed"), "provider_unavailable"),
    ],
)
async def test_meter_and_provider_failures_keep_abstract_preview_provenance(
    monkeypatch, failure, expected_reason
):
    fake = _FakeLLM()
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)

    async def fail_meter(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(summary_agent_module, "invoke_metered", fail_meter)
    result = await summary_agent_func(_papers(1), _cb, max_summaries=1)
    assert result[0]["summary_status"] == "abstract_preview"
    assert result[0]["summary_fallback_reason"] == expected_reason
    assert result[0]["difficulty"] is None
    assert result[0]["summary_contributions"] == []


@pytest.mark.asyncio
async def test_invalid_provider_summary_has_invalid_output_provenance(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr(summary_agent_module, "get_llm", lambda agent, model_override=None: fake)

    async def invalid_meter(*_args, **_kwargs):
        return type("R", (), {"content": '{"tldr":"", "difficulty":"other", "contributions":[]}'})()

    monkeypatch.setattr(summary_agent_module, "invoke_metered", invalid_meter)
    result = await summary_agent_func(_papers(1), _cb, max_summaries=1)
    assert result[0]["summary_status"] == "abstract_preview"
    assert result[0]["summary_fallback_reason"] == "invalid_output"
    assert result[0]["difficulty"] is None


@pytest.mark.asyncio
async def test_unavailable_llm_marks_every_summary_as_billing_unavailable(monkeypatch):
    monkeypatch.setattr(
        summary_agent_module,
        "get_llm",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("meter unavailable")),
    )
    result = await summary_agent_func(_papers(2), _cb, max_summaries=1)
    assert all(paper["summary_status"] == "abstract_preview" for paper in result)
    assert all(paper["summary_fallback_reason"] == "billing_unavailable" for paper in result)
