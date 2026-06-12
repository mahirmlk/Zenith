import pytest
from services.retry import async_retry


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
