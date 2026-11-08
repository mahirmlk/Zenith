import pytest
from agents import orchestrator
from agents.orchestrator import run_orchestrator
from models.schemas import AgentStep


@pytest.mark.asyncio
async def test_run_orchestrator_basic():
    steps = []

    async def callback(step: AgentStep):
        steps.append(step)

    result = await run_orchestrator("test-run-1", "machine learning", callback)
    assert result.run_id == "test-run-1"
    assert isinstance(result.papers, list)
    # Should have at least orchestrator start and complete steps
    assert any(s.agent == "orchestrator" for s in steps)


@pytest.mark.asyncio
async def test_graph_exception_does_not_become_success(monkeypatch):
    steps = []

    async def callback(step: AgentStep):
        steps.append(step)

    class BrokenGraph:
        async def ainvoke(self, *_args, **_kwargs):
            raise RuntimeError("provider failure")

    monkeypatch.setattr(orchestrator, "_get_graph", lambda: BrokenGraph())

    with pytest.raises(RuntimeError, match="provider failure"):
        await run_orchestrator("failed-run", "query", callback)

    assert any(step.agent == "orchestrator" and step.status == "error" for step in steps)
    assert not any(step.agent == "orchestrator" and step.status == "complete" for step in steps)


@pytest.mark.asyncio
async def test_node_failure_does_not_become_success(monkeypatch):
    steps = []

    async def callback(step: AgentStep):
        steps.append(step)

    class FailedNodeGraph:
        async def ainvoke(self, state, **_kwargs):
            return {**state, "failed_agents": ["research"]}

    monkeypatch.setattr(orchestrator, "_get_graph", lambda: FailedNodeGraph())

    with pytest.raises(RuntimeError, match="failed in: research"):
        await run_orchestrator("failed-node-run", "query", callback)

    assert any(step.agent == "orchestrator" and step.status == "error" for step in steps)
    assert not any(step.agent == "orchestrator" and step.status == "complete" for step in steps)
