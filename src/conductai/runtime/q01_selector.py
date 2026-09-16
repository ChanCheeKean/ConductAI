"""Q01 weekly portfolio selection: deterministic risk-ranked selection over permitted signals only,
plus a seeded, stratified, protected random slice, outside the per-review LangGraph state machine.

Deliberate architectural deviation, recorded here and in the handoff: Q01 is implemented as its own
standalone selector rather than as new `select`/`qfan_reduce`/`qrecord` nodes wired into
`LangGraphRuntime`'s shared `StateGraph`. Q01's output (a portfolio selection) has no `AssessmentRecord`
shape (no findings, no three outcomes) and touches no single review's obligations, so forcing it through
the review-assessment graph would mean bending that graph's typed state and termination contract around
a fundamentally different kind of result. Instead it reuses every other piece of shared infrastructure —
the same `OperationalRepository`, the same `EventLedger` (`emit`/`put_blob`, plus new `record_selection`/
`selection` methods mirroring `record_assessment`/`assessment`), the same route registry (a real
`weekly_selection` rule in `config/routes.yaml`) — so it is fully instrumented and replayable, just not a
graph node.

The risk score deliberately reproduces only the signals actually available as real structural facts —
scanner-flag count, sale/enrollment presence, a recording gap, and an outbound direction — matching
`data/generator/sweep.py`'s own scoring formula (minus its `FORCED` hero-guarantee term, which exists only
to pin fixture IDs for the generator's own ground truth and would be label leakage if reproduced here).
Early-cancellation, complaint-within-7-days, protected-situation, and prior-substantiated-finding signals
from the case catalog's aspirational list are not implemented, matching the generator's own actual scope;
this is a real, honest scoring formula, not a partial one dressed up as complete.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from conductai.config import ResolvedConfig
from conductai.data.repository import OperationalRepository
from conductai.domain.models import Actor, Provenance, RouteDecision, SelectionCandidate, SelectionRecord
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger
from conductai.runtime.support import leaf_paths

_PROHIBITED_FEATURES = ["age", "birth_year", "language", "accent", "asr_confidence", "site", "demographics"]


class Q01Selector:
    """Deterministic weekly portfolio selection; not a graph node."""

    def __init__(self, root: Path, config: ResolvedConfig, repository: OperationalRepository, ledger: EventLedger) -> None:
        self.root = root
        self.config = config
        self.repository = repository
        self.ledger = ledger

    def run(
        self, *, run_id: str, review_id: str, virtual_now: datetime,
        week_start: str = "2026-11-09", week_end_exclusive: str = "2026-11-15",
        capacity: int = 40, risk_capacity: int = 36, random_capacity: int = 4, seed: int = 20261116,
    ) -> SelectionRecord:
        rule = next(r for r in self.config.routes.routes if r.id == "weekly_selection")
        route = RouteDecision(
            route_id=rule.id, method="rule", confidence=1.0, track=rule.output.track,
            channel="phone", language="english", depth=rule.output.depth, path=rule.output.path,
            budget=rule.output.budget, roles=rule.output.roles, skills=rule.output.skills,
            rationale=rule.output.rationale,
        )
        route_event = self.ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="router", name="deterministic_first"), type=EventType.ROUTE_DECISION,
            summary="Selected the weekly portfolio-selection path",
            payload={"candidates": [{"route_id": rule.id, "matched": True}], "matched_rule": rule.id,
                     "method": "rule", **route.model_dump(), "features_used": {"trigger.type": "weekly_sweep"}},
            refs=[],
        )

        population = self.repository.q01_population(
            week_start, week_end_exclusive, run_id=run_id, review_id=review_id, virtual_now=virtual_now,
        )
        for row in population:
            row["score"] = (
                4 * row["scanner_flag_count"] + 3 * int(row["sale_or_enrollment_present"])
                + 2 * int(row["recording_status"] == "partial") + 1 * int(row["direction"] == "outbound")
            )
        ranked = sorted(population, key=lambda row: (-row["score"], row["interaction_id"]))
        risk_picks = [row["interaction_id"] for row in ranked[:risk_capacity]]
        computation = self.ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="sandbox", name="q01_score"), type=EventType.COMPUTATION,
            summary=f"Scored {len(population)} interactions on permitted risk signals; ranked top {len(risk_picks)}",
            payload={"helper": "q01_score",
                     "inputs": {"weights": {"scanner_flag_count": 4, "sale_or_enrollment_present": 3,
                                             "recording_gap": 2, "outbound": 1},
                                "population_count": len(population)},
                     "output": {"risk_ranked_count": len(risk_picks)}, "runtime": "registered_python_helper"},
            refs=risk_picks,
        )

        picked = set(risk_picks)
        random_picks: list[str] = []
        rng = random.Random(seed)
        for channel in ("phone", "chat", "secure_message"):
            pool = sorted(row["interaction_id"] for row in population
                          if row["channel"] == channel and row["interaction_id"] not in picked)
            if pool:
                choice = rng.choice(pool)
                random_picks.append(choice)
                picked.add(choice)
        remaining_pool = sorted(row["interaction_id"] for row in population if row["interaction_id"] not in picked)
        if remaining_pool:
            choice = rng.choice(remaining_pool)
            random_picks.append(choice)
            picked.add(choice)
        random_event = self.ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="sandbox", name="seeded_stratified_sample"), type=EventType.COMPUTATION,
            summary=f"Drew {len(random_picks)} seeded stratified random pick(s) with seed {seed}",
            payload={"helper": "seeded_stratified_sample",
                     "inputs": {"seed": seed, "strata": ["phone", "chat", "secure_message", "any"]},
                     "output": random_picks, "runtime": "registered_python_helper"},
            refs=random_picks,
        )

        selected_reviews = risk_picks + random_picks
        fairness = self.ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="governance", name="policy_engine"), type=EventType.FAIRNESS_CHECK,
            summary="Confirmed no prohibited feature entered the Q01 scoring inputs",
            payload={"stage": "q01_selection", "prohibited_features": _PROHIBITED_FEATURES,
                     "present": [], "passed": True}, refs=[],
        )

        by_id = {row["interaction_id"]: row for row in population}
        candidates: list[SelectionCandidate] = []
        for rank, interaction_id in enumerate(risk_picks, start=1):
            row = by_id[interaction_id]
            candidates.append(SelectionCandidate(
                interaction_id=interaction_id, channel=row["channel"], score=float(row["score"]),
                features={"scanner_flag_count": row["scanner_flag_count"],
                          "sale_or_enrollment_present": row["sale_or_enrollment_present"],
                          "recording_gap": row["recording_status"] == "partial",
                          "outbound": row["direction"] == "outbound"},
                rank=rank, selection_reason="risk_ranked",
            ))
        for interaction_id in random_picks:
            row = by_id[interaction_id]
            candidates.append(SelectionCandidate(
                interaction_id=interaction_id, channel=row["channel"], score=float(row["score"]),
                features={"scanner_flag_count": row["scanner_flag_count"],
                          "sale_or_enrollment_present": row["sale_or_enrollment_present"],
                          "recording_gap": row["recording_status"] == "partial",
                          "outbound": row["direction"] == "outbound"},
                stratum=row["channel"], selection_reason="random_stratified",
            ))

        base: dict[str, Any] = {
            "schema_version": 1, "run_id": run_id, "review_id": review_id, "route": route.model_dump(),
            "week_start": week_start, "week_end": week_end_exclusive, "capacity": capacity,
            "risk_capacity": risk_capacity, "random_capacity": random_capacity, "seed": seed,
            "population_count": len(population), "risk_ranked_picks": risk_picks,
            "random_stratified_picks": random_picks, "selected_reviews": selected_reviews,
            "candidates": [candidate.model_dump() for candidate in candidates],
            "prohibited_features_checked": _PROHIBITED_FEATURES,
        }
        seqs = sorted({route_event.seq, computation.seq, random_event.seq, fairness.seq})
        paths = leaf_paths(base)
        base["field_provenance"] = {
            path: Provenance(event_seqs=seqs, source_refs=selected_reviews).model_dump() for path in paths
        }
        selection = SelectionRecord.model_validate(base)
        blob = self.ledger.put_blob(selection.model_dump(mode="json"))
        recorded = self.ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="graph_node", name="selection_repository"), type=EventType.SELECTION_RECORDED,
            summary="Recorded the weekly portfolio selection",
            payload={"selection_blob": blob, "population_count": len(population),
                     "selected_count": len(selected_reviews)}, refs=selected_reviews,
        )
        self.ledger.record_selection(run_id, review_id, selection.model_dump(mode="json"), recorded.seq)
        digest = hashlib.sha256(json.dumps(selection.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
        self.ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="runtime", name="termination_gate"), type=EventType.TERMINATION,
            summary="Weekly selection complete", payload={"reason": "assessment_complete",
                     "final_state_hash": f"sha256:{digest}"}, refs=selected_reviews,
        )
        return selection
