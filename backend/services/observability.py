"""Observability: Langfuse tracing and Sentry error tracking.

Both integrations are optional and only initialise when the relevant
environment variables are configured, so local/dev runs are unaffected.
"""
import logging
from functools import lru_cache
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_langfuse_handler() -> Any | None:
    """Return a Langfuse callback handler for LangChain/LangGraph runs.

    Returns None when Langfuse is not configured. The handler is cached so
    every graph run in the process shares one client.
    """
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    try:
        from langfuse.callback import CallbackHandler

        return CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as exc:
        logger.warning("Langfuse initialisation failed, tracing disabled: %s", exc)
        return None


def get_langfuse_config() -> dict[str, Any]:
    """Build the ``config`` dict to pass to a LangGraph ``ainvoke`` call."""
    handler = get_langfuse_handler()
    if handler is None:
        return {}
    return {"callbacks": [handler]}


def init_sentry() -> None:
    """Initialise Sentry for error tracking if a DSN is configured."""
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            environment=settings.app_env,
            release="ai-paper-agent-backend",
        )
        logger.info("Sentry initialised")
    except Exception as exc:
        logger.warning("Sentry initialisation failed: %s", exc)