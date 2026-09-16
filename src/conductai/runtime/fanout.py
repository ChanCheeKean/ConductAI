"""Bounded, deterministic fan-out over branch subjects.

No hosted async subagent control plane is used (architecture §4.3, §20): each branch is
evaluated synchronously by a deterministic callback, but the full fan-out/subagent/merge
event shape is emitted exactly as it would be for a real dispatcher, so the trajectory
signals (`fanout_started`, `subagent_started`/`subagent_finished`, `fanout_merged`) are
real, not decorative. Branches merge in stable `subject_id` order regardless of how they
were produced.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from conductai.domain.models import Actor
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger


class FanOutCapExceeded(RuntimeError):
    pass


class FanOutDispatcher:
    """Runs one bounded fan-out and returns branch results merged in stable order."""

    def __init__(self, ledger: EventLedger) -> None:
        self._ledger = ledger

    def run(
        self, *, kind: str, role: str, subjects: list[str], cap: int,
        evaluate: Callable[[str], dict[str, Any]], run_id: str, review_id: str, virtual_now: datetime,
    ) -> tuple[list[dict[str, Any]], list[int]]:
        if len(subjects) > cap:
            raise FanOutCapExceeded(f"{kind} fan-out over cap: {len(subjects)} > {cap}")
        ordered = sorted(subjects)
        seqs: list[int] = []
        started = self._ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="runtime", name="fanout_dispatcher"), type=EventType.FANOUT_STARTED,
            summary=f"Started {kind} fan-out over {len(ordered)} branch(es)",
            payload={"kind": kind, "count": len(ordered), "cap": cap}, refs=list(ordered),
        )
        seqs.append(started.seq)
        results: list[dict[str, Any]] = []
        for subject in ordered:
            branch_id = f"BR-{kind}-{subject}"
            brief_blob = self._ledger.put_blob({"subject": subject, "role": role})
            begin = self._ledger.emit(
                run_id=run_id, review_id=review_id, virtual_now=virtual_now,
                actor=Actor(kind="subagent", name=role), type=EventType.SUBAGENT_STARTED,
                summary=f"Evaluating branch {subject}",
                payload={"role": role, "subject": subject, "brief_blob": brief_blob},
                branch_id=branch_id, parent_span_id=started.span_id, refs=[subject],
            )
            seqs.append(begin.seq)
            result = evaluate(subject)
            result_blob = self._ledger.put_blob(result)
            end = self._ledger.emit(
                run_id=run_id, review_id=review_id, virtual_now=virtual_now,
                actor=Actor(kind="subagent", name=role), type=EventType.SUBAGENT_FINISHED,
                summary=f"Branch {subject} result: {result.get('status', 'ok')}",
                payload={"role": role, "subject": subject, "result_blob": result_blob, "status": "ok"},
                branch_id=branch_id, parent_span_id=started.span_id, refs=[subject],
            )
            seqs.append(end.seq)
            results.append({"subject": subject, **result})
        merged_hash = self._ledger.put_blob(results)
        merged = self._ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="runtime", name="fanout_reducer"), type=EventType.FANOUT_MERGED,
            summary=f"Merged {len(results)} {kind} branch result(s)",
            payload={"branches": len(results), "ordering": "subject_id", "result_hash": merged_hash},
            refs=list(ordered),
        )
        seqs.append(merged.seq)
        return results, seqs
