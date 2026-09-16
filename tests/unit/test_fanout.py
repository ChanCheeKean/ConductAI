from datetime import UTC, datetime

import pytest

from conductai.observability.ledger import EventLedger
from conductai.runtime.fanout import FanOutCapExceeded, FanOutDispatcher


def test_fanout_merges_branches_in_stable_subject_order(tmp_path):
    path = tmp_path / "run.sqlite"
    ledger = EventLedger(path, {"mode": "test"})
    dispatcher = FanOutDispatcher(ledger)
    calls: list[str] = []

    def evaluate(subject: str) -> dict:
        calls.append(subject)
        return {"consent": subject.endswith("2")}

    results, seqs = dispatcher.run(
        kind="linked_interaction", role="linked_interaction_reviewer",
        subjects=["INT-3", "INT-1", "INT-2"], cap=24, evaluate=evaluate,
        run_id="RUN-FANOUT", review_id="REV-2026-90013", virtual_now=datetime(2026, 11, 16, 15, tzinfo=UTC),
    )
    assert calls == ["INT-1", "INT-2", "INT-3"]
    assert [row["subject"] for row in results] == ["INT-1", "INT-2", "INT-3"]
    assert results[1]["consent"] is True
    events = ledger.events("RUN-FANOUT")
    types = [event.type.value for event in events]
    assert types[0] == "fanout_started"
    assert types[-1] == "fanout_merged"
    assert types.count("subagent_started") == 3
    assert types.count("subagent_finished") == 3
    branch_ids = {event.branch_id for event in events if event.type.value in {"subagent_started", "subagent_finished"}}
    assert branch_ids == {"BR-linked_interaction-INT-1", "BR-linked_interaction-INT-2", "BR-linked_interaction-INT-3"}
    root_span = events[0].span_id
    assert all(
        event.parent_span_id == root_span for event in events if event.type.value == "subagent_started"
    )
    assert seqs == [event.seq for event in events]


def test_fanout_rejects_subject_count_over_cap(tmp_path):
    path = tmp_path / "run.sqlite"
    ledger = EventLedger(path, {"mode": "test"})
    dispatcher = FanOutDispatcher(ledger)
    with pytest.raises(FanOutCapExceeded):
        dispatcher.run(
            kind="linked_interaction", role="linked_interaction_reviewer",
            subjects=[f"INT-{i}" for i in range(25)], cap=24, evaluate=lambda subject: {},
            run_id="RUN-CAP", review_id="REV-2026-90013", virtual_now=datetime(2026, 11, 16, 15, tzinfo=UTC),
        )
