"""Adapter registry: integration_type -> adapter factory.

Extension point for future adapters (e.g., a KODI-specific adapter): implement
``TargetAdapter`` and register it here. No engine changes required.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.integrations.base import TargetAdapter
from app.integrations.mock_adapter import MockAdapter
from app.integrations.rest_adapter import RestAdapter

AdapterFactory = Callable[[dict[str, Any]], TargetAdapter]


def _make_mock(config: dict[str, Any]) -> TargetAdapter:
    return MockAdapter(
        config=config.get("adapter_config", {}),
        capabilities=config.get("capabilities"),
    )


def _make_rest(config: dict[str, Any]) -> TargetAdapter:
    connection = config.get("connection", {})
    return RestAdapter(
        base_url=connection.get("base_url", ""),
        auth=config.get("_credentials"),
        capabilities=config.get("capabilities"),
        invoke_path=connection.get("invoke_path", ""),
    )


_REGISTRY: dict[str, AdapterFactory] = {
    "mock": _make_mock,
    "rest_api": _make_rest,
}


def register_adapter(integration_type: str, factory: AdapterFactory) -> None:
    """Register a new adapter type (public extension point)."""
    _REGISTRY[integration_type] = factory


def get_adapter(integration_type: str, config: dict[str, Any]) -> TargetAdapter:
    """Build an adapter for ``integration_type``; raises on unknown types."""
    factory = _REGISTRY.get(integration_type)
    if factory is None:
        raise ValueError(f"No adapter registered for integration type '{integration_type}'")
    return factory(config)
