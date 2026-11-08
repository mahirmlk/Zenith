import pytest
from types import SimpleNamespace
from typing import TypedDict
from agents import orchestrator
from agents.orchestrator import run_orchestrator
from models.schemas import AgentStep
from services.run_store import PostgresRunStore


@pytest.mark.asyncio
async def test_run_orchestrator_basic(monkeypatch):
    steps = []

    async def callback(step: AgentStep):
        steps.append(step)

    class FakeGraph:
        async def aget_state(self, _config):
            return SimpleNamespace(config={"configurable": {"thread_id": "test-run-1"}}, values={}, next=())

        async def ainvoke(self, state, **_kwargs):
            return state

    monkeypatch.setattr(orchestrator, "_get_graph", lambda: FakeGraph())

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


def _initial_state():
    return {
        "run_id": "run-1",
        "query": "query",
        "user_id": "user-1",
        "model": None,
        "raw_papers": [],
        "enriched_papers": [],
        "ranked_papers": [],
        "steps": [],
        "failed_agents": [],
    }


@pytest.mark.asyncio
async def test_checkpoint_recovery_starts_from_initial_state_when_no_checkpoint():
    class Graph:
        def __init__(self):
            self.called_with = []

        async def aget_state(self, _config):
            return SimpleNamespace(config={"configurable": {"thread_id": "run-1"}}, values={}, next=())

        async def ainvoke(self, state, *, config):
            self.called_with.append((state, config))
            return state

    graph = Graph()
    initial = _initial_state()
    config = {"configurable": {"thread_id": "run-1"}}

    result = await orchestrator._invoke_or_resume(graph, initial, config)

    assert result is initial
    assert graph.called_with == [(initial, config)]


@pytest.mark.asyncio
async def test_checkpoint_recovery_resumes_pending_nodes_with_none_input():
    final_state = {**_initial_state(), "ranked_papers": [{"id": "p1"}]}

    class Graph:
        def __init__(self):
            self.called_with = []

        async def aget_state(self, _config):
            return SimpleNamespace(
                config={"configurable": {"thread_id": "run-1", "checkpoint_id": "cp-1"}},
                values=_initial_state(),
                next=("summary",),
            )

        async def ainvoke(self, state, *, config):
            self.called_with.append((state, config))
            return final_state

    graph = Graph()
    config = {"configurable": {"thread_id": "run-1"}}

    result = await orchestrator._invoke_or_resume(graph, _initial_state(), config)

    assert result is final_state
    assert graph.called_with == [(None, config)]


@pytest.mark.asyncio
async def test_checkpoint_recovery_uses_terminal_state_without_reexecuting_graph():
    completed_state = {**_initial_state(), "ranked_papers": [{"id": "p1"}]}

    class Graph:
        async def aget_state(self, _config):
            return SimpleNamespace(
                config={"configurable": {"thread_id": "run-1", "checkpoint_id": "cp-done"}},
                values=completed_state,
                next=(),
            )

        async def ainvoke(self, *_args, **_kwargs):
            raise AssertionError("terminal checkpoint must not re-execute graph nodes")

    result = await orchestrator._invoke_or_resume(
        Graph(), _initial_state(), {"configurable": {"thread_id": "run-1"}}
    )

    assert result is completed_state


@pytest.mark.asyncio
async def test_checkpoint_recovery_rejects_checkpoint_owned_by_another_request():
    class Graph:
        async def aget_state(self, _config):
            foreign_state = {**_initial_state(), "user_id": "another-user"}
            return SimpleNamespace(
                config={"configurable": {"thread_id": "run-1", "checkpoint_id": "cp-foreign"}},
                values=foreign_state,
                next=("summary",),
            )

        async def ainvoke(self, *_args, **_kwargs):
            raise AssertionError("mismatched checkpoint must not resume")

    with pytest.raises(RuntimeError, match="does not match"):
        await orchestrator._invoke_or_resume(
            Graph(), _initial_state(), {"configurable": {"thread_id": "run-1"}}
        )


@pytest.mark.asyncio
async def test_real_langgraph_memory_checkpoint_resumes_after_node_failure():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.constants import END, START
    from langgraph.graph import StateGraph

    class State(TypedDict, total=False):
        run_id: str
        user_id: str
        query: str
        model: str | None
        first_node_complete: bool
        done: bool

    calls = {"first": 0, "second": 0}

    async def first_node(_state):
        calls["first"] += 1
        return {"first_node_complete": True}

    async def second_node(_state):
        calls["second"] += 1
        if calls["second"] == 1:
            raise RuntimeError("simulated worker crash")
        return {"done": True}

    builder = StateGraph(State)
    builder.add_node("first", first_node)
    builder.add_node("second", second_node)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    graph = builder.compile(checkpointer=MemorySaver())
    initial = {
        "run_id": "run-1",
        "user_id": "user-1",
        "query": "query",
        "model": None,
    }
    config = {"configurable": {"thread_id": "run-1"}}

    with pytest.raises(RuntimeError, match="simulated worker crash"):
        await orchestrator._invoke_or_resume(graph, initial, config)

    resumed = await orchestrator._invoke_or_resume(graph, initial, config)

    assert resumed["done"] is True
    assert calls == {"first": 1, "second": 2}


@pytest.mark.asyncio
async def test_production_checkpointer_fails_closed_without_database_url(monkeypatch):
    monkeypatch.setattr(orchestrator, "_checkpointer", None)
    monkeypatch.setattr(orchestrator, "_checkpointer_context", None)

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        await orchestrator.start_checkpointer(production=True)


@pytest.mark.asyncio
async def test_postgres_checkpointer_context_is_setup_and_closed(monkeypatch):
    events = []

    class Saver:
        async def setup(self):
            events.append("setup")

    class Context:
        async def __aenter__(self):
            events.append("enter")
            return Saver()

        async def __aexit__(self, *_args):
            events.append("exit")

    monkeypatch.setattr(orchestrator, "_checkpointer", None)
    monkeypatch.setattr(orchestrator, "_checkpointer_context", None)
    monkeypatch.setattr(orchestrator, "_durable_checkpointer", False)

    await orchestrator.start_checkpointer(
        "postgresql://test",
        production=True,
        saver_context_factory=lambda _url: Context(),
    )
    assert orchestrator.has_durable_checkpointer()
    assert events == ["enter", "setup"]

    await orchestrator.stop_checkpointer()

    assert not orchestrator.has_durable_checkpointer()
    assert events == ["enter", "setup", "exit"]


@pytest.mark.asyncio
async def test_checkpointer_setup_failure_closes_connection_context(monkeypatch):
    events = []

    class Saver:
        async def setup(self):
            events.append("setup")
            raise RuntimeError("schema setup failed")

    class Context:
        async def __aenter__(self):
            events.append("enter")
            return Saver()

        async def __aexit__(self, *_args):
            events.append("exit")

    monkeypatch.setattr(orchestrator, "_checkpointer", None)
    monkeypatch.setattr(orchestrator, "_checkpointer_context", None)

    with pytest.raises(RuntimeError, match="checkpoint schema"):
        await orchestrator.start_checkpointer(
            "postgresql://test",
            production=True,
            saver_context_factory=lambda _url: Context(),
        )

    assert events == ["enter", "setup", "exit"]
    assert not orchestrator.has_durable_checkpointer()


@pytest.mark.asyncio
async def test_expired_checkpoint_cleanup_only_deletes_terminal_run_threads(monkeypatch):
    from services import run_store as run_store_module

    class Query:
        def __init__(self):
            self.statuses = None
            self.offset = 0
            self.page_size = 0

        def select(self, *_args):
            return self

        def in_(self, _key, values):
            self.statuses = values
            return self

        def lt(self, *_args):
            return self

        def order(self, *_args):
            return self

        def range(self, start, end):
            self.offset = start
            self.page_size = end - start + 1
            return self

        async def execute(self):
            assert self.statuses == ["complete", "failed", "cancelled"]
            rows = [{"id": "terminal-run"}]
            return SimpleNamespace(data=rows[self.offset : self.offset + self.page_size])

    class Database:
        def table(self, name):
            assert name == "research_runs"
            return Query()

    store = object.__new__(PostgresRunStore)
    store._ttl = 60
    store._database = Database()

    class Saver:
        def __init__(self):
            self.deleted = []

        async def adelete_thread(self, thread_id):
            self.deleted.append(thread_id)

    saver = Saver()

    async def get_store():
        return store

    monkeypatch.setattr(run_store_module, "get_run_store", get_store)
    monkeypatch.setattr(orchestrator, "_checkpointer", saver)
    monkeypatch.setattr(orchestrator, "_durable_checkpointer", True)

    deleted = await orchestrator.cleanup_expired_checkpoints(batch_size=10)

    assert deleted == 1
    assert saver.deleted == ["terminal-run"]
