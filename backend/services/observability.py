"""Observability: Langfuse tracing and Sentry error tracking.

Both integrations are optional and only initialise when the relevant
environment variables are configured, so local/dev runs are unaffected.
"""
import logging
import re
from functools import lru_cache
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|sk-ant-[A-Za-z0-9_\-]{8,}|AIza[A-Za-z0-9_\-]{10,}"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
    r"|Bearer\s+\S+|api[_-]?key\s*[:=]\s*\S+|sb_secret_[A-Za-z0-9_\-]+)",
    re.I,
)


def mask_sensitive(value: Any) -> Any:
    """Langfuse mask: redact secrets, truncate long texts (paper full
    text is not traced verbatim — update.md §7.2)."""
    if isinstance(value, str):
        value = _SECRET_RE.sub("[REDACTED]", value)
        return value[:2000] + ("…[truncated]" if len(value) > 2000 else "")
    if isinstance(value, dict):
        return {k: mask_sensitive(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_sensitive(v) for v in value]
    return value


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

        try:
            return CallbackHandler(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                mask=mask_sensitive,
            )
        except TypeError:
            # Never send traces when redaction is unavailable. A dependency
            # upgrade or an unexpected callback API must not silently turn
            # on unmasked prompt/document capture.
            logger.warning("Langfuse mask unsupported; tracing disabled")
            return None
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
            send_default_pii=False,
        )
        logger.info("Sentry initialised")
    except Exception as exc:
        logger.warning("Sentry initialisation failed: %s", exc)
