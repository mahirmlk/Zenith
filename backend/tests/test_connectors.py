"""Connector registry tests (update.md §13)."""
from services.connectors import REGISTRY, enabled_connectors, get_connector


def test_registry_only_reviewed_connectors():
    assert "github-readonly" in REGISTRY
    assert get_connector("arbitrary-user-mcp") is None


def test_nothing_enabled_by_default():
    assert enabled_connectors() == []
