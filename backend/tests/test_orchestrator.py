import pytest
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
