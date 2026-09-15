"""Shared helpers used by every scenario workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def node_context(state: dict[str, Any]) -> dict[str, Any]:
    return {"run_id": state["run_id"], "review_id": state["review_id"],
            "virtual_now": datetime.fromisoformat(state["virtual_now"].replace("Z", "+00:00")).astimezone(UTC)}


def leaf_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in value.items():
            paths.extend(leaf_paths(item, f"{prefix}.{key}" if prefix else key))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(leaf_paths(item, f"{prefix}[{index}]"))
        return paths or [prefix]
    return [prefix]
