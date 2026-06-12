import asyncio
import logging

logger = logging.getLogger(__name__)

RETRIABLE_EXCEPTIONS = (ConnectionError, TimeoutError)

async def async_retry(func, max_retries: int = 3, base_delay: float = 1.0):
    """Retry an async function with exponential backoff."""
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except RETRIABLE_EXCEPTIONS as exc:
            last_exception = exc
            if attempt == max_retries:
                break
            delay = base_delay * (2 ** attempt)
            logger.warning("Retry %s/%s after %ss: %s", attempt + 1, max_retries, delay, exc)
            await asyncio.sleep(delay)
        except Exception:
            raise  # Raise immediately, do not retry for non-transient errors
    raise last_exception
