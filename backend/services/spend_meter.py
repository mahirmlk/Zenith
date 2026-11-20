"""Fail-closed provider-spend reservations and per-attempt settlement."""
from __future__ import annotations

import json
import asyncio
import contextvars
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any

import httpx

from config import get_settings
from services.openrouter_catalog import CATALOG_VERSION, EMBEDDING_CATALOG_VERSION, MODEL_PRICES
from services.supabase_client import get_supabase


class SpendMeterError(RuntimeError):
    """The call could not be safely admitted or its spend could not be settled."""


class SpendLimitExceeded(SpendMeterError):
    """The current billing subject has reached a spend cap."""


@dataclass(frozen=True)
class ProviderUsage:
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    cost_micros: int


@dataclass(frozen=True)
class PendingGenerationLookup:
    generation_id: str


@dataclass(frozen=True)
class BillingContext:
    subject_id: str
    run_id: str | None
    operation: str
    operation_id: str = field(default_factory=lambda: str(uuid.uuid4()))


_billing_context: contextvars.ContextVar[BillingContext | None] = contextvars.ContextVar(
    "billing_context", default=None
)


def set_billing_context(context: BillingContext) -> contextvars.Token[BillingContext | None]:
    if not context.subject_id or not context.operation:
        raise ValueError("Billing subject and operation are required")
    return _billing_context.set(context)


def reset_billing_context(token: contextvars.Token[BillingContext | None]) -> None:
    _billing_context.reset(token)


def _context(explicit: BillingContext | None) -> BillingContext:
    context = explicit or _billing_context.get()
    if context is None:
        raise SpendMeterError("Provider call has no billing identity")
    return context


def input_token_upper_bound(messages: list[Any]) -> int:
    """Bound the text-only serialized request by bytes plus message framing.

    This endpoint currently accepts text-only LangChain messages. Bounding
    each message to 64 KiB and the complete serialized request to 1 MiB makes
    byte count a conservative tokenizer-independent upper bound, with an
    extra 32 tokens per message for provider framing.
    """
    if not messages or len(messages) > 64:
        raise SpendMeterError("Provider request has an unsupported message count")
    encoded_messages: list[dict[str, str]] = []
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, str):
            raise SpendMeterError("Metered provider requests must be text-only")
        role = getattr(message, "type", message.__class__.__name__)
        encoded = content.encode("utf-8")
        if len(encoded) > 65_536:
            raise SpendMeterError("Provider message exceeds the metered byte limit")
        encoded_messages.append({"role": str(role), "content": content})
    serialized_bytes = len(json.dumps(encoded_messages, ensure_ascii=False).encode("utf-8"))
    if serialized_bytes > 1_048_576:
        raise SpendMeterError("Provider request exceeds the metered byte limit")
    return serialized_bytes + len(messages) * 32


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, str)):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number >= 0 else None


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


async def record_provider_reference(
    attempt_id: str, generation_id: str | None, request_id: str | None
) -> None:
    await _rpc(
        "record_model_spend_reference",
        {
            "p_attempt_id": attempt_id,
            "p_generation_id": generation_id,
            "p_request_id": request_id,
        },
    )


async def _rpc(name: str, params: dict[str, Any]) -> Any:
    try:
        supabase = await get_supabase()
        response = await supabase.rpc(name, params).execute()
    except Exception as exc:
        raise SpendMeterError("Spend ledger is unavailable") from exc
    return response.data


async def meter_ready() -> bool:
    try:
        return bool(await _rpc("model_spend_meter_ready", {}))
    except SpendMeterError:
        return False


async def reserve_attempt(
    *,
    context: BillingContext,
    attempt_id: str,
    model: str,
    max_output_tokens: int,
    input_token_bound: int,
) -> int:
    price = MODEL_PRICES.get(model)
    if price is None:
        raise SpendMeterError(f"No verified price bound is available for model {model}")
    settings = get_settings()
    daily_cap = settings.llm_daily_spend_cap_usd_micros
    monthly_cap = settings.llm_monthly_spend_cap_usd_micros
    if daily_cap <= 0 or monthly_cap <= 0:
        raise SpendMeterError("Daily and monthly spend caps must be configured above zero")
    reservation = price.maximum_cost_micros(max_output_tokens, input_token_bound)
    result = await _rpc(
        "reserve_model_spend",
        {
            "p_attempt_id": attempt_id,
            "p_subject_id": context.subject_id,
            "p_run_id": context.run_id,
            "p_operation_id": context.operation_id,
            "p_operation": context.operation,
            "p_requested_model": model,
            "p_catalog_version": CATALOG_VERSION,
            "p_reserved_micros": reservation,
            "p_daily_cap_micros": daily_cap,
            "p_monthly_cap_micros": monthly_cap,
        },
    )
    if not result:
        raise SpendLimitExceeded("Provider spend limit reached")
    return reservation


async def mark_unknown(attempt_id: str, reason: str) -> None:
    try:
        await _rpc(
            "mark_model_spend_unknown",
            {"p_attempt_id": attempt_id, "p_reason": reason[:120]},
        )
    except SpendMeterError:
        # The initial reservation remains durable. Failure to mark its state
        # must not release it or obscure the original provider failure.
        return


async def settle_attempt(
    *,
    attempt_id: str,
    actual_model: str,
    actual_provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    actual_cost_micros: int,
) -> None:
    result = await _rpc(
        "settle_model_spend",
        {
            "p_attempt_id": attempt_id,
            "p_actual_model": actual_model,
            "p_actual_provider": actual_provider,
            "p_prompt_tokens": prompt_tokens,
            "p_completion_tokens": completion_tokens,
            "p_actual_cost_micros": actual_cost_micros,
        },
    )
    if not result:
        raise SpendMeterError("Spend settlement was rejected; reservation retained")


def _extract_metadata(response: Any) -> ProviderUsage | PendingGenerationLookup | None:
    metadata = _dict(getattr(response, "response_metadata", None))
    usage = _dict(metadata.get("usage"))
    token_usage = _dict(metadata.get("token_usage"))
    if not usage:
        usage = token_usage
    prompt = _as_int(usage.get("prompt_tokens", token_usage.get("prompt_tokens")))
    completion = _as_int(usage.get("completion_tokens", token_usage.get("completion_tokens")))
    cost_value = usage.get("cost")
    if cost_value is None:
        cost_value = token_usage.get("cost")
    try:
        cost_micros = int(
            (Decimal(str(cost_value)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING)
        )
    except (InvalidOperation, ValueError, TypeError):
        cost_micros = -1
    model = metadata.get("model_name") or metadata.get("model")
    provider = metadata.get("provider_name") or metadata.get("provider")
    openrouter_metadata = _dict(metadata.get("openrouter_metadata"))
    endpoints = _dict(openrouter_metadata.get("endpoints"))
    available = endpoints.get("available")
    if isinstance(available, list):
        selected = next(
            (item for item in available if isinstance(item, dict) and item.get("selected") is True),
            None,
        )
        if isinstance(selected, dict):
            provider = selected.get("provider") or provider
            model = selected.get("model") or model
    generation_id = metadata.get("id") or getattr(response, "id", None)
    if isinstance(model, str) and isinstance(provider, str) and prompt is not None and completion is not None and cost_micros >= 0:
        return ProviderUsage(model, provider, prompt, completion, cost_micros)
    if isinstance(generation_id, str) and generation_id.startswith("gen-"):
        return PendingGenerationLookup(generation_id)
    return None


async def _lookup_generation(generation_id: str) -> ProviderUsage | None:
    settings = get_settings()
    if not settings.openrouter_api_key:
        return None
    async with httpx.AsyncClient(timeout=5.0) as client:
        for delay in (0.0, 0.25, 0.75):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = await client.get(
                    "https://openrouter.ai/api/v1/generation",
                    params={"id": generation_id},
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                )
                response.raise_for_status()
                data = _dict(_dict(response.json()).get("data"))
                model = data.get("model")
                provider = data.get("provider_name")
                prompt = _as_int(data.get("tokens_prompt"))
                completion = _as_int(data.get("tokens_completion"))
                cost = data.get("total_cost", data.get("usage"))
                cost_micros = int(
                    (Decimal(str(cost)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING)
                )
                if isinstance(model, str) and isinstance(provider, str) and prompt is not None and completion is not None and cost_micros >= 0:
                    return ProviderUsage(model, provider, prompt, completion, cost_micros)
            except (httpx.HTTPError, ValueError, TypeError, InvalidOperation):
                continue
    return None


async def invoke_metered(
    llm: Any,
    messages: list[Any],
    *,
    model: str,
    max_output_tokens: int,
    context: BillingContext | None = None,
    timeout_seconds: float | None = None,
) -> Any:
    """Reserve, perform exactly one visible provider attempt, and settle it."""
    billing = _context(context)
    attempt_id = str(uuid.uuid4())
    await reserve_attempt(
        context=billing,
        attempt_id=attempt_id,
        model=model,
        max_output_tokens=max_output_tokens,
        input_token_bound=input_token_upper_bound(messages),
    )
    try:
        invocation = llm.ainvoke(messages)
        response = (
            await asyncio.wait_for(invocation, timeout=timeout_seconds)
            if timeout_seconds is not None
            else await invocation
        )
        response_metadata = _dict(getattr(response, "response_metadata", None))
        external_id = response_metadata.get("id") or getattr(response, "id", None)
        generation_id = response_metadata.get("generation_id")
        request_id = response_metadata.get("request_id")
        if isinstance(external_id, str):
            if external_id.startswith("gen-"):
                generation_id = generation_id or external_id
            else:
                request_id = request_id or external_id
        if isinstance(generation_id, str) or isinstance(request_id, str):
            await record_provider_reference(
                attempt_id,
                generation_id if isinstance(generation_id, str) else None,
                request_id if isinstance(request_id, str) else None,
            )
        metadata = _extract_metadata(response)
        if isinstance(metadata, PendingGenerationLookup):
            metadata = await _lookup_generation(metadata.generation_id)
        if metadata is None:
            raise SpendMeterError("Provider response has no authoritative model, provider, usage, and cost")
        await settle_attempt(
            attempt_id=attempt_id,
            actual_model=metadata.model,
            actual_provider=metadata.provider,
            prompt_tokens=metadata.prompt_tokens,
            completion_tokens=metadata.completion_tokens,
            actual_cost_micros=metadata.cost_micros,
        )
        return response
    except BaseException as exc:
        await mark_unknown(attempt_id, type(exc).__name__)
        raise


async def reserve_embedding_attempt(
    *, context: BillingContext, attempt_id: str, max_input_tokens: int,
) -> int:
    settings = get_settings()
    if settings.llm_daily_spend_cap_usd_micros <= 0 or settings.llm_monthly_spend_cap_usd_micros <= 0:
        raise SpendMeterError("Daily and monthly spend caps must be configured above zero")
    from services.openrouter_catalog import embedding_cost_micros

    amount = embedding_cost_micros(max_input_tokens)
    result = await _rpc(
        "reserve_model_spend",
        {
            "p_attempt_id": attempt_id,
            "p_subject_id": context.subject_id,
            "p_run_id": context.run_id,
            "p_operation_id": context.operation_id,
            "p_operation": context.operation,
            "p_requested_model": "openai/" + "text-embedding-3-small",
            "p_catalog_version": EMBEDDING_CATALOG_VERSION,
            "p_reserved_micros": amount,
            "p_daily_cap_micros": settings.llm_daily_spend_cap_usd_micros,
            "p_monthly_cap_micros": settings.llm_monthly_spend_cap_usd_micros,
        },
    )
    if not result:
        raise SpendLimitExceeded("Provider spend limit reached")
    return amount


async def settle_embedding_attempt(
    *, attempt_id: str, tokens: int, actual_cost_micros: int,
) -> None:
    await settle_attempt(
        attempt_id=attempt_id,
        actual_model="text-embedding-3-small",
        actual_provider="OpenAI",
        prompt_tokens=tokens,
        completion_tokens=0,
        actual_cost_micros=actual_cost_micros,
    )


async def anonymize_subject(subject_id: str) -> None:
    result = await _rpc(
        "anonymize_model_spend_subject", {"p_subject_id": subject_id}
    )
    if result is False:
        raise SpendMeterError("Could not anonymize provider spend ledger owner")
