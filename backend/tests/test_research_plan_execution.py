"""Focused safety and lifecycle coverage for durable research-plan runs."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers.research import ResearchRequest, execute_research_plan
from services import job_queue
from services import research_plan_execution as execution


def _state(**overrides):
    state = {
        "run_id": "run-1",
        "user_id": "user-1",
        "query": "retrieval evidence",
        "project_id": None,
        "source_scope": "public_corpus",
        "task_type": "deep_research",
        "max_sources": 10,
        "max_tool_calls": 6,
        "max_wall_clock_seconds": 90,
        "max_model_calls": 2,
        "max_output_tokens": 1800,
        "synthesis_enabled": True,
        "deadline_at": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
        "logical_tool_calls": 0,
        "papers": [],
        "sources": [],
        "evidence": [],
        "comparison": [],
        "gaps": [],
        "synthesis": [],
        "steps": [],
    }
    state.update(overrides)
    return state


def test_graph_has_bounded_plan_nodes_and_typed_state(monkeypatch):
    monkeypatch.setattr("agents.orchestrator._get_checkpointer", lambda: None)
    graph = execution._graph()
    node_names = set(graph.get_graph().nodes)

    assert {"retrieve_sources", "extract_evidence", "compare_sources", "identify_gaps", "synthesize"}.issubset(node_names)
    assert execution.MAX_PLAN_SOURCES == 10


def test_exact_evidence_uses_canonical_paper_and_offset_citation():
    state = _state(
        query="retrieval evidence",
        papers=[{
            "id": "paper-1",
            "title": "Retrieval",
            "abstract": "Retrieval evidence improves ranking.",
        }],
    )

    evidence = execution._abstract_evidence(state)

    assert len(evidence) == 1
    item = evidence[0]
    assert item.citation_id == f"paper-1:{item.start_offset}:{item.end_offset}"
    assert item.sentence == state["papers"][0]["abstract"][item.start_offset:item.end_offset]


def test_synthesis_caps_disable_calls_unless_both_calls_and_tokens_fit():
    assert execution._synthesis_within_budget(_state()) is True
    assert execution._synthesis_within_budget(_state(max_model_calls=1)) is False
    assert execution._synthesis_within_budget(_state(max_output_tokens=1799)) is False


@pytest.mark.asyncio
async def test_worker_dispatch_uses_persisted_metadata_when_flag_changes(monkeypatch):
    calls = []
    state = SimpleNamespace(
        status="pending", user_id="user-1", query="query", model="__research_plan_execution__"
    )

    class Store:
        async def get(self, _run_id):
            return state

        async def try_start(self, _run_id):
            state.status = "running"
            return True

        async def release(self, _run_id):
            return None

        async def update(self, _run_id, status=None, results=None):
            state.status = status or state.status

    async def heartbeat(_run_id):
        await __import__("asyncio").Event().wait()

    async def get_plan(_run_id):
        return {"run_id": "run-1"}

    async def plan_run(run_id, user_id, query):
        calls.append(("plan", run_id, user_id, query))

    async def normal_run(*args):
        calls.append(("normal", *args))

    monkeypatch.setattr("services.run_store.run_store", Store())
    monkeypatch.setattr("services.research_plan_execution.get_plan_execution", get_plan)
    monkeypatch.setattr("services.research_plan_execution.run_plan_execution", plan_run)
    monkeypatch.setattr("services.research_plan_execution.is_missing_plan_execution_table", lambda _exc: False)
    monkeypatch.setattr("routers.stream._run_once", normal_run)
    monkeypatch.setattr("services.job_queue._heartbeat_run", heartbeat)
    monkeypatch.setattr("config.get_settings", lambda: SimpleNamespace(research_plan_execution_enabled=False))

    handled = await asyncio.wait_for(job_queue._execute_run("run-1"), timeout=5)

    assert handled is True
    assert calls == [("plan", "run-1", "user-1", "query")]


class _InsertQuery:
    def __init__(self, db):
        self.db = db

    def insert(self, value):
        self.db.inserted = value
        return self

    async def execute(self):
        return SimpleNamespace(data=self.db.inserted)


class _Db:
    inserted = None

    def table(self, _name):
        return _InsertQuery(self)


class _MetadataDb:
    def __init__(self, project_id):
        self.project_id = project_id

    def table(self, _name):
        return self

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def maybe_single(self):
        return self

    async def execute(self):
        return SimpleNamespace(data={"project_id": self.project_id})


@pytest.mark.asyncio
async def test_execute_endpoint_disabled_before_any_database_work(monkeypatch):
    monkeypatch.setattr("routers.research.get_settings", lambda: SimpleNamespace(research_plan_execution_enabled=False))

    with pytest.raises(HTTPException) as error:
        await execute_research_plan(ResearchRequest(query="retrieval"), object(), None, {"user_id": "user-1"}, _Db())

    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_idempotent_replay_rejects_different_project_scope(monkeypatch):
    class Store:
        async def find_idempotent(self, *_args):
            return SimpleNamespace(
                run_id="existing-run",
                query="same query",
                model="__research_plan_execution__",
            )

    monkeypatch.setattr("routers.research.get_settings", lambda: SimpleNamespace(
        research_plan_execution_enabled=True, research_synthesis_enabled=False,
    ))
    monkeypatch.setattr("routers.research.run_store", Store())

    with pytest.raises(HTTPException) as error:
        await execute_research_plan(
            ResearchRequest(query="same query"),
            object(),
            "same-key",
            {"user_id": "user-1"},
            _MetadataDb("project-1"),
        )

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_execute_endpoint_persists_contract_and_enqueues_shared_run(monkeypatch):
    db = _Db()
    calls = []

    class Store:
        async def find_idempotent(self, *_args):
            return None

        async def create(self, run_id, query, **kwargs):
            calls.append(("create", run_id, query, kwargs))
            return SimpleNamespace(run_id=run_id, query=query)

        async def update(self, *args, **kwargs):
            calls.append(("update", args, kwargs))

    async def consume(*args, **kwargs):
        calls.append(("consume", args, kwargs))
        return True

    async def enqueue(run_id):
        calls.append(("enqueue", run_id))

    monkeypatch.setattr("routers.research.get_settings", lambda: SimpleNamespace(
        research_plan_execution_enabled=True, research_synthesis_enabled=False,
    ))
    monkeypatch.setattr("routers.research.run_store", Store())
    monkeypatch.setattr("routers.research.budget.consume", consume)
    monkeypatch.setattr("services.job_queue.enqueue", enqueue)

    accepted = await execute_research_plan(
        ResearchRequest(query="compare retrieval A and B"),
        object(),
        "client-request-1",
        {"user_id": "user-1"},
        db,
    )

    assert accepted.run_id
    assert db.inserted["run_id"] == accepted.run_id
    assert db.inserted["task_type"] == "compare"
    assert db.inserted["max_sources"] == 10
    assert db.inserted["max_tool_calls"] == 4
    assert db.inserted["max_wall_clock_seconds"] == 45
    assert db.inserted["source_scope"] == "public_corpus"
    assert [item[0] for item in calls if isinstance(item, tuple)] == ["consume", "create", "enqueue"]


@pytest.mark.asyncio
async def test_execute_endpoint_enqueue_failure_marks_run_failed_and_refunds(monkeypatch):
    calls = []

    class Store:
        async def find_idempotent(self, *_args):
            return None

        async def create(self, run_id, query, **_kwargs):
            return SimpleNamespace(run_id=run_id, query=query)

        async def update(self, run_id, status=None):
            calls.append(("failed", run_id, status))

        async def delete_run(self, run_id):
            calls.append(("delete", run_id))

    async def consume(*_args, **_kwargs):
        return True

    async def refund(*_args, **_kwargs):
        calls.append(("refund",))

    async def enqueue(_run_id):
        raise ConnectionError("queue unavailable")

    monkeypatch.setattr("routers.research.get_settings", lambda: SimpleNamespace(
        research_plan_execution_enabled=True, research_synthesis_enabled=False,
    ))
    monkeypatch.setattr("routers.research.run_store", Store())
    monkeypatch.setattr("routers.research.budget.consume", consume)
    monkeypatch.setattr("routers.research.budget.refund", refund)
    monkeypatch.setattr("services.job_queue.enqueue", enqueue)

    with pytest.raises(HTTPException) as error:
        await execute_research_plan(ResearchRequest(query="papers on retrieval"), object(), None, {"user_id": "user-1"}, _Db())

    assert error.value.status_code == 503
    assert calls[0] == ("delete", calls[0][1])
    assert calls[1] == ("refund",)


def test_migration_cascades_run_cleanup_and_is_service_only():
    migration = Path("supabase/migrations/0019_durable_research_plan_execution.sql").read_text()
    deletion = Path("backend/services/account_deletion.py").read_text()

    assert "REFERENCES public.research_runs(id) ON DELETE CASCADE" in migration
    assert "REVOKE ALL ON public.research_plan_executions FROM PUBLIC, anon, authenticated" in migration
    assert "run_store.delete_run(run_id)" in deletion

