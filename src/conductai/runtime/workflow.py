"""Scenario dispatch behind the runtime-neutral workflow surface."""

from __future__ import annotations

from typing import Any


class WorkflowDispatcher:
    def __init__(self, workflows: dict[str, Any]) -> None:
        self._workflows = workflows

    def _workflow(self, state: dict[str, Any]) -> Any:
        try:
            return self._workflows[state["scenario_id"]]
        except KeyError as exc:
            raise RuntimeError(f"scenario is not implemented: {state['scenario_id']}") from exc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        def dispatch(state: dict[str, Any]) -> dict[str, Any]:
            return getattr(self._workflow(state), name)(state)

        return dispatch
