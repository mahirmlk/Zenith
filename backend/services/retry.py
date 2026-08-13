import asyncio
import logging
from typing import Awaitable, Callable, Optional, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Builtin + HTTP-layer transient errors. httpx.HTTPError covers connect/read
# timeouts, connection resets, and 5xx HTTPStatusError responses.
RETRIABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    httpx.HTTPError,
)

# Vendor LLM/embedding SDKs raise their own transient error types
# (openai.APIConnectionError, anthropic.RateLimitError, google.api_core
# Unavailable, ...). Match by class-name fragment to avoid hard imports of
# optional providers.
_RETRIABLE_NAME_FRAGMENTS = (
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "RateLimitError",
    "InternalServerError",
    "InternalError",
    "BadGateway",
    "ServiceUnavailable",
    "GatewayTimeout",
    "ConnectError",
    "ReadTimeout",
    "RemoteProtocolError",
    "TransportError",
    "TooManyRequests",
    "TemporaryFailure",
    "Unavailable",
)


def is_retriable(exc: BaseException) -> bool:
    """Return True if ``exc`` represents a transient failure worth retrying."""
    if isinstance(exc, RETRIABLE_EXCEPTIONS):
        return True
    return any(fragment in type(exc).__name__ for fragment in _RETRIABLE_NAME_FRAGMENTS)


async def async_retry(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> T:
    """Retry an async function with exponential backoff on transient errors.

    Non-transient exceptions (ValueError, JSON decode errors, etc.) are
    re-raised immediately.
    """
    last_exception: Optional[BaseException] = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as exc:
            if not is_retriable(exc):
                raise
            last_exception = exc
            if attempt == max_retries:
                break
            delay = base_delay * (2 ** attempt)
            logger.warning("Retry %s/%s after %ss: %s", attempt + 1, max_retries, delay, exc)
            await asyncio.sleep(delay)
    assert last_exception is not None
    raise last_exception