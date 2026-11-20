from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from services import spend_meter
from services.spend_meter import BillingContext, SpendMeterError


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openrouter_api_key="test-key",
        llm_daily_spend_cap_usd_micros=10_000_000,
        llm_monthly_spend_cap_usd_micros=100_000_000,
    )


def _response(cost: str = "0.00001") -> Any:
    return SimpleNamespace(
        id="chatcmpl-test",
        response_metadata={
            "id": "chatcmpl-test",
            "model_name": "anthropic/claude-sonnet-5.5-20260928",
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "cost": cost},
            "openrouter_metadata": {
                "endpoints": {
                    "available": [{"model": "anthropic/claude-sonnet-5.5", "provider": "Anthropic", "selected": True}]
                }
            },
        },
    )


@pytest.mark.asyncio
async def test_request_bound_is_serialized_utf8_bytes_plus_framing() -> None:
    messages = [HumanMessage(content="abc"), HumanMessage(content="é")]
    bound = spend_meter.input_token_upper_bound(messages)
    assert bound == len('[{"role": "human", "content": "abc"}, {"role": "human", "content": "é"}]'.encode()) + 64
    with pytest.raises(SpendMeterError, match="message exceeds"):
        spend_meter.input_token_upper_bound([HumanMessage(content="x" * 65_537)])
    with pytest.raises(SpendMeterError, match="text-only"):
        spend_meter.input_token_upper_bound([HumanMessage(content=[{"type": "text", "text": "x"}])])


@pytest.mark.asyncio
async def test_atomic_concurrent_reservations_and_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spend_meter, "get_settings", _settings)
    lock = asyncio.Lock()
    used: dict[str, int] = {}
    attempts: dict[str, dict[str, Any]] = {}

    async def rpc(_name: str, params: dict[str, Any]) -> bool:
        async with lock:
            attempt_id = params["p_attempt_id"]
            existing = attempts.get(attempt_id)
            if existing:
                assert existing["p_subject_id"] == params["p_subject_id"]
                return True
            subject = params["p_subject_id"]
            reservation = params["p_reserved_micros"]
            if used.get(subject, 0) + reservation > 150:
                return False
            used[subject] = used.get(subject, 0) + reservation
            attempts[attempt_id] = params
            return True

    monkeypatch.setattr(spend_meter, "_rpc", rpc)
    context = BillingContext("u1", "00000000-0000-0000-0000-000000000001", "summary")
    ids = ["00000000-0000-0000-0000-000000000002", "00000000-0000-0000-0000-000000000003"]
    results = await asyncio.gather(
        *[
            spend_meter.reserve_attempt(
                context=context, attempt_id=attempt_id, model="anthropic/claude-sonnet-5.5",
                max_output_tokens=10, input_token_bound=1,
            )
            for attempt_id in ids
        ],
        return_exceptions=True,
    )
    assert sum(isinstance(item, int) for item in results) == 1
    assert sum(isinstance(item, SpendMeterError) for item in results) == 1
    assert len(attempts) == 1
    # An RPC retry for the same attempt remains a single reservation.
    reserved = await spend_meter.reserve_attempt(
        context=context, attempt_id=next(iter(attempts)), model="anthropic/claude-sonnet-5.5",
        max_output_tokens=10, input_token_bound=1,
    )
    assert reserved == used["u1"]


@pytest.mark.asyncio
async def test_timeout_retains_unknown_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spend_meter, "get_settings", _settings)
    calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(name: str, params: dict[str, Any]) -> bool:
        calls.append((name, params))
        return True

    async def fail(_messages: list[Any], **_kwargs: Any) -> Any:
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(spend_meter, "_rpc", rpc)
    with pytest.raises(TimeoutError):
        await spend_meter.invoke_metered(
            SimpleNamespace(ainvoke=fail), [HumanMessage(content="test")],
            model="anthropic/claude-sonnet-5.5", max_output_tokens=10,
            context=BillingContext("u1", None, "test"),
        )
    assert [name for name, _ in calls] == ["reserve_model_spend", "mark_model_spend_unknown"]


@pytest.mark.asyncio
async def test_retries_create_distinct_attempts_and_settle_authoritative_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spend_meter, "get_settings", _settings)
    calls: list[tuple[str, dict[str, Any]]] = []
    invocation = 0

    async def rpc(name: str, params: dict[str, Any]) -> bool:
        calls.append((name, params))
        return True

    async def invoke(_messages: list[Any], **_kwargs: Any) -> Any:
        nonlocal invocation
        invocation += 1
        if invocation == 1:
            raise TimeoutError("retry me")
        return _response()

    monkeypatch.setattr(spend_meter, "_rpc", rpc)
    async def retry() -> Any:
        for _ in range(2):
            try:
                return await spend_meter.invoke_metered(
                    SimpleNamespace(ainvoke=invoke), [HumanMessage(content="short prompt")],
                    model="anthropic/claude-sonnet-5.5", max_output_tokens=10,
                    context=BillingContext("u1", None, "test"),
                )
            except TimeoutError:
                continue
        raise AssertionError("retry did not complete")

    assert await retry() is not None
    reservations = [params["p_attempt_id"] for name, params in calls if name == "reserve_model_spend"]
    assert len(reservations) == 2 and reservations[0] != reservations[1]
    assert any(name == "mark_model_spend_unknown" for name, _ in calls)
    settlement = next(params for name, params in calls if name == "settle_model_spend")
    assert settlement["p_actual_provider"] == "Anthropic"
    assert settlement["p_prompt_tokens"] == 12
    assert settlement["p_completion_tokens"] == 5
    assert settlement["p_actual_cost_micros"] == 10


@pytest.mark.asyncio
async def test_reservation_rpc_failure_prevents_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spend_meter, "get_settings", _settings)

    async def rpc(*_args: Any) -> Any:
        raise SpendMeterError("ledger down")

    async def invoke(*_args: Any, **_kwargs: Any) -> Any:
        pytest.fail("provider call ran after reservation failure")

    monkeypatch.setattr(spend_meter, "_rpc", rpc)
    with pytest.raises(SpendMeterError):
        await spend_meter.invoke_metered(
            SimpleNamespace(ainvoke=invoke), [HumanMessage(content="test")],
            model="anthropic/claude-sonnet-5.5", max_output_tokens=10,
            context=BillingContext("u1", None, "test"),
        )


@pytest.mark.asyncio
async def test_generation_lookup_failure_never_settles_partial_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spend_meter, "get_settings", _settings)
    calls: list[tuple[str, dict[str, Any]]] = []

    async def rpc(name: str, params: dict[str, Any]) -> bool:
        calls.append((name, params))
        return True

    async def no_generation(_generation_id: str) -> None:
        return None

    async def invoke(_messages: list[Any]) -> Any:
        return SimpleNamespace(
            id="gen-abc",
            response_metadata={
                "id": "gen-abc",
                "model_name": "anthropic/claude-sonnet-5.5",
                "token_usage": {"prompt_tokens": 8, "completion_tokens": 3},
            },
        )

    monkeypatch.setattr(spend_meter, "_rpc", rpc)
    monkeypatch.setattr(spend_meter, "_lookup_generation", no_generation)
    with pytest.raises(SpendMeterError, match="no authoritative"):
        await spend_meter.invoke_metered(
            SimpleNamespace(ainvoke=invoke), [HumanMessage(content="test")],
            model="anthropic/claude-sonnet-5.5", max_output_tokens=10,
            context=BillingContext("u1", None, "test"),
        )
    assert not any(name == "settle_model_spend" for name, _ in calls)
    assert any(name == "mark_model_spend_unknown" for name, _ in calls)
