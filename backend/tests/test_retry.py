import httpx
import pytest
from services.retry import async_retry, is_retriable


@pytest.mark.asyncio
async def test_retry_success():
    call_count = 0

    async def func():
        nonlocal call_count
        call_count += 1
        return "success"

    result = await async_retry(func, max_retries=3, base_delay=0.01)
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_eventual_success():
    call_count = 0

    async def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("not yet")
        return "done"

    result = await async_retry(func, max_retries=3, base_delay=0.01)
    assert result == "done"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_exhausted():
    async def func():
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError, match="always fails"):
        await async_retry(func, max_retries=2, base_delay=0.01)


def test_is_retriable_httpx_errors():
    assert is_retriable(httpx.ConnectError("boom", request=httpx.Request("GET", "http://x")))
    assert is_retriable(httpx.ReadTimeout("boom", request=httpx.Request("GET", "http://x")))


def test_is_retriable_vendor_sdk_errors():
    class APIConnectionError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    class ValueErrorOnly(Exception):
        pass

    assert is_retriable(APIConnectionError("connection"))
    assert is_retriable(RateLimitError("429"))
    assert not is_retriable(ValueErrorOnly("bad payload"))


@pytest.mark.asyncio
async def test_retry_vendor_sdk_transient_error():
    call_count = 0

    class APIConnectionError(Exception):
        pass

    async def func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise APIConnectionError("transient")
        return "ok"

    result = await async_retry(func, max_retries=3, base_delay=0.01)
    assert result == "ok"
    assert call_count == 3
