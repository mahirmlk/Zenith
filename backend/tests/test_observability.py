from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from services import observability


def _install_callback(monkeypatch: Any, callback: type[Any]) -> None:
    package = ModuleType("langfuse")
    setattr(package, "__path__", [])
    callback_module = ModuleType("langfuse.callback")
    callback_module.CallbackHandler = callback  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", package)
    monkeypatch.setitem(sys.modules, "langfuse.callback", callback_module)


def test_langfuse_disables_tracing_if_redaction_is_unsupported(monkeypatch: Any) -> None:
    class UnmaskedOnlyHandler:
        def __init__(self, *, public_key: str, secret_key: str, host: str) -> None:
            self.public_key = public_key

    _install_callback(monkeypatch, UnmaskedOnlyHandler)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "public-test-key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret-test-key")
    observability.get_langfuse_handler.cache_clear()

    try:
        assert observability.get_langfuse_handler() is None
    finally:
        observability.get_langfuse_handler.cache_clear()


def test_langfuse_handler_receives_redaction_callback(monkeypatch: Any) -> None:
    class RedactingHandler:
        def __init__(self, **kwargs: Any) -> None:
            self.mask = kwargs["mask"]

    _install_callback(monkeypatch, RedactingHandler)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "public-test-key")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret-test-key")
    observability.get_langfuse_handler.cache_clear()

    try:
        handler = observability.get_langfuse_handler()
        assert handler is not None
        assert handler.mask is observability.mask_sensitive
        assert handler.mask("Bearer abcdefgh") == "[REDACTED]"
    finally:
        observability.get_langfuse_handler.cache_clear()
