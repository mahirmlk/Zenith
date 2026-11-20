from types import SimpleNamespace

import pytest

from models.schemas import AgentStep, PaperSearchResult
from routers import stream


@pytest.mark.asyncio
async def test_late_orchestrator_result_is_suppressed_after_cancel(monkeypatch):
    emitted: list[tuple[str, dict]] = []

    class CancelledStore:
        async def get(self, run_id: str):
            return SimpleNamespace(status="cancelled")

        async def add_event(self, run_id: str, event: str, data: dict):
            emitted.append((event, data))

    async def finish_after_cancel(*args, **kwargs):
        return PaperSearchResult(papers=[], run_id="run-1")

    monkeypatch.setattr(stream, "run_store", CancelledStore())
    monkeypatch.setattr(stream, "run_orchestrator", finish_after_cancel)
    stream._running_tasks["run-1"] = object()

    await stream._run_once("run-1", "query", "user-1", None)

    assert emitted == [("cancelled", {"run_id": "run-1"})]
    assert "run-1" not in stream._running_tasks


@pytest.mark.asyncio
async def test_cancelled_orchestrator_steps_are_not_appended(monkeypatch):
    emitted: list[tuple[str, dict]] = []

    class CancelledStore:
        async def get(self, run_id: str):
            return SimpleNamespace(status="cancelled")

        async def add_event(self, run_id: str, event: str, data: dict):
            emitted.append((event, data))

    async def emit_then_finish(run_id, query, callback, **kwargs):
        await callback(AgentStep(agent="research", status="complete"))
        return PaperSearchResult(papers=[], run_id=run_id)

    monkeypatch.setattr(stream, "run_store", CancelledStore())
    monkeypatch.setattr(stream, "run_orchestrator", emit_then_finish)

    await stream._run_once("run-2", "query", "user-1", None)

    assert emitted == [("cancelled", {"run_id": "run-2"})]
