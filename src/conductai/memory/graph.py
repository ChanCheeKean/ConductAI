"""Registered-template graph reads over the persistent-source graph projection.

LadybugDB is the designed embedded-Cypher backend; this environment has no LadybugDB
driver available, so the startup probe fails and every run records an explicit,
never-silent `fallback` event before falling back to an identical-contract NetworkX
projection built from the same persistent source edges (`data/generated/graph/*.jsonl`).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import networkx as nx

from conductai.domain.models import Actor
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger


class GraphRepository:
    """Bounded multi-hop relationship reads; arbitrary Cypher never reaches the graph store."""

    def __init__(self, graph_root: Path, ledger: EventLedger) -> None:
        self._ledger = ledger
        self._backend, self._probe_error = self._probe_backend()
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        with (graph_root / "nodes.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                self._graph.add_node(row["node_id"], label=row["label"], key=row["key"], **row.get("props", {}))
        with (graph_root / "edges.jsonl").open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                self._graph.add_edge(row["src"], row["dst"], rel=row["rel"], **row.get("props", {}))
        self._reported_fallback: set[str] = set()

    @staticmethod
    def _probe_backend() -> tuple[str, str | None]:
        try:
            import ladybugdb  # type: ignore  # noqa: F401
        except ImportError as exc:
            return "networkx", str(exc)
        return "ladybugdb", None

    def _emit_fallback_once(self, *, run_id: str, review_id: str, virtual_now: datetime) -> None:
        if self._backend != "networkx" or run_id in self._reported_fallback:
            return
        self._reported_fallback.add(run_id)
        self._ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="data", name="graph_backend"), type=EventType.FALLBACK,
            summary="LadybugDB driver unavailable; graph memory served from the NetworkX projection",
            payload={"component": "graph_memory", "from": "ladybugdb", "to": "networkx",
                     "reason": self._probe_error, "run_snapshot_flag": "graph_backend=networkx_fallback"},
        )

    _TEMPLATES = {
        "callback_chain_for_fulfilling_interaction",
        "customer_interaction_history",
    }

    def query_graph(
        self, template_id: str, parameters: dict[str, Any], as_of: str, max_hops: int, limit: int, **context: Any,
    ) -> list[dict[str, Any]]:
        if template_id not in self._TEMPLATES:
            raise KeyError(template_id)
        self._emit_fallback_once(run_id=context["run_id"], review_id=context["review_id"], virtual_now=context["virtual_now"])
        if template_id == "callback_chain_for_fulfilling_interaction":
            rows = self._callback_chain(parameters["interaction_id"])
        else:
            rows = self._customer_interaction_history(parameters["customer_id"], parameters.get("before_at", as_of))
        rows = rows[:limit]
        node_ids = sorted({row["_path"][-1] for row in rows} | {row["_path"][0] for row in rows})
        self._ledger.emit(
            run_id=context["run_id"], review_id=context["review_id"], virtual_now=context["virtual_now"],
            actor=Actor(kind="data", name="graph_query"), type=EventType.GRAPH_QUERY,
            summary=f"Executed registered graph template {template_id}",
            payload={"template_id": template_id, "parameters": parameters, "max_hops": max_hops,
                     "backend": self._backend, "node_ids": node_ids},
            refs=node_ids,
        )
        return [{key: value for key, value in row.items() if key != "_path"} for row in rows]

    def _callback_chain(self, fulfilling_interaction_id: str) -> list[dict[str, Any]]:
        target = f"Interaction:{fulfilling_interaction_id}"
        rows: list[dict[str, Any]] = []
        for src, dst, data in self._graph.in_edges(target, data=True):
            if data["rel"] != "FULFILLED_BY":
                continue
            callback_request_id = self._graph.nodes[src]["key"]
            for _, origin, origin_data in self._graph.out_edges(src, data=True):
                if origin_data["rel"] != "CREATED_IN":
                    continue
                origin_id = self._graph.nodes[origin]["key"]
                rows.append({
                    "callback_request_id": callback_request_id,
                    "fulfilled_by_interaction_id": fulfilling_interaction_id,
                    "created_in_interaction_id": origin_id,
                    "_path": [src, origin],
                })
        return rows

    def _customer_interaction_history(self, customer_id: str, before_at: str) -> list[dict[str, Any]]:
        source = f"Customer:{customer_id}"
        rows: list[dict[str, Any]] = []
        for _, dst, data in self._graph.out_edges(source, data=True):
            if data["rel"] != "PARTICIPATED" or data.get("role") != "customer":
                continue
            node = self._graph.nodes[dst]
            started_at = node.get("started_at_utc")
            if started_at is None or started_at >= before_at:
                continue
            rows.append({
                "interaction_id": node["key"], "channel": node.get("channel"), "started_at_utc": started_at,
                "_path": [source, dst],
            })
        rows.sort(key=lambda row: row["started_at_utc"])
        return rows
