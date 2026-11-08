"""Daily search budget tests without a live Redis service."""
from types import SimpleNamespace

import pytest

from services import budget


class FakeRedis:
    def __init__(self):
        self.counts = {}
        self.ttls = {}

    async def eval(self, _script, _key_count, key, limit, ttl):
        current = self.counts.get(key, 0)
        if current >= int(limit):
            return 0
        current += 1
        self.counts[key] = current
        if current == 1:
            self.ttls[key] = int(ttl)
        return 1


@pytest.mark.asyncio
async def test_redis_budget_enforces_limit_and_isolates_user_and_day(monkeypatch):
    fake = FakeRedis()
    current_day = "2026-11-08"
    monkeypatch.setattr(
        budget,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://redis", app_env="production"),
    )
    monkeypatch.setattr(budget, "_get_redis_client", lambda _url: _return(fake))
    monkeypatch.setattr(budget, "_utc_day_and_ttl", lambda now=None: (current_day, 1234))

    assert await budget.consume("user-a", 2) is True
    assert await budget.consume("user-a", 2) is True
    assert await budget.consume("user-a", 2) is False
    assert await budget.consume("user-b", 2) is True
    first_user_key = next(key for key in fake.counts if "2026-11-08" in key)
    assert fake.ttls[first_user_key] == 1234

    current_day = "2026-11-09"
    assert await budget.consume("user-a", 2) is True
    assert len(fake.counts) == 3


@pytest.mark.asyncio
async def test_production_budget_fails_closed_when_redis_is_not_configured(monkeypatch):
    monkeypatch.setattr(
        budget,
        "get_settings",
        lambda: SimpleNamespace(redis_url="", app_env="production"),
    )

    with pytest.raises(budget.BudgetUnavailableError, match="required"):
        await budget.consume("user-a", 1)


@pytest.mark.asyncio
async def test_production_budget_fails_closed_when_redis_errors(monkeypatch):
    async def unavailable(_url):
        raise ConnectionError("test connection failure")

    monkeypatch.setattr(
        budget,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://redis", app_env="production"),
    )
    monkeypatch.setattr(budget, "_get_redis_client", unavailable)

    with pytest.raises(budget.BudgetUnavailableError, match="unavailable"):
        await budget.consume("user-a", 1)


@pytest.mark.asyncio
async def test_development_budget_falls_back_to_process_local_counter(monkeypatch):
    async def unavailable(_url):
        raise ConnectionError("test connection failure")

    monkeypatch.setattr(
        budget,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://redis", app_env="development"),
    )
    monkeypatch.setattr(budget, "_get_redis_client", unavailable)
    budget.reset_for_tests()

    assert await budget.consume("user-a", 1) is True
    assert await budget.consume("user-a", 1) is False


async def _return(value):
    return value
