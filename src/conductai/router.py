"""Data-driven deterministic-first route evaluation."""

from __future__ import annotations

from typing import Any

from conductai.config import RoutesConfig
from conductai.domain.models import RouteDecision


def choose_route(config: RoutesConfig, trigger: dict[str, Any], facts: dict[str, Any]) -> tuple[RouteDecision, list[dict[str, Any]]]:
    permitted: dict[str, Any] = {"trigger.type": trigger.get("type")}
    for key, value in facts.items():
        if value is None or isinstance(value, (bool, str, int, float)):
            permitted[key] = value
    evaluated: list[dict[str, Any]] = []
    chosen = None
    for rule in config.routes:
        if rule.match.get("fallback"):
            matched = True
        else:
            checks = rule.match.get("all", [])
            matched = all(_evaluate(check, permitted) for check in checks)
        evaluated.append({"route_id": rule.id, "matched": matched})
        if matched:
            chosen = rule
            break
    if chosen is None:
        raise RuntimeError("route registry has no match or fallback")
    interaction = facts["interaction"]
    language = "english" if interaction["detected_language"] == "en" else "spanish"
    method = "fallback" if chosen.match.get("fallback") else "rule"
    decision = RouteDecision(
        route_id=chosen.id, method=method, confidence=1.0 if method == "rule" else 0.0,
        track=chosen.output.track, channel=interaction["channel"], language=language,
        depth=chosen.output.depth, path=chosen.output.path, budget=chosen.output.budget,
        roles=chosen.output.roles, skills=chosen.output.skills, rationale=chosen.output.rationale,
    )
    return decision, evaluated


def _evaluate(check: dict[str, Any], permitted: dict[str, Any]) -> bool:
    key = check.get("field") or check.get("fact")
    value = permitted.get(key)
    operation = check.get("op")
    expected = check.get("value")
    if operation == "eq":
        return value == expected
    if operation == "in":
        return value in expected
    raise ValueError(f"unknown route operator: {operation}")
