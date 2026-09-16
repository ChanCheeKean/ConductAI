from datetime import UTC, datetime

import pytest

from conductai.harness import ArtifactHarness
from conductai.observability.ledger import EventLedger


def test_artifact_request_and_release_are_idempotent(project_root, tmp_path):
    path = tmp_path / "run.sqlite"
    ledger = EventLedger(path, {"mode": "test"})
    harness = ArtifactHarness(project_root / "data/generated", path, ledger)
    arguments = {
        "artifact_id": "RTX-9000101",
        "interaction_id": "INT-9000101",
        "kind": "retranscription",
        "respond_by": "2026-11-27T23:59:59Z",
        "idempotency_key": "REV-2026-90001:RTX-9000101",
        "run_id": "RUN-IDEMPOTENT",
        "review_id": "REV-2026-90001",
        "virtual_now": datetime(2026, 11, 16, 15, tzinfo=UTC),
    }
    first = harness.request_artifact(**arguments)
    second = harness.request_artifact(**arguments)
    assert first["status"] == "requested"
    assert second["status"] == "already_requested"
    assert len([event for event in ledger.events("RUN-IDEMPOTENT") if event.type.value == "artifact_requested"]) == 1
    release_one = harness.release_next("RUN-IDEMPOTENT")
    release_two = harness.release_next("RUN-IDEMPOTENT")
    assert release_one == release_two
    assert release_one["virtual_now"] == "2026-11-16T19:00:00Z"
    assert release_one["artifact"]["retranscription_id"] == "RTX-9000101"
    harness.acknowledge_release("RUN-IDEMPOTENT", "RTX-9000101", release_one["virtual_now"])
    with pytest.raises(LookupError):
        harness.release_next("RUN-IDEMPOTENT")


def test_colleague_statement_release_advances_one_business_day(project_root, tmp_path):
    path = tmp_path / "run.sqlite"
    ledger = EventLedger(path, {"mode": "test"})
    harness = ArtifactHarness(project_root / "data/generated", path, ledger)
    request = harness.request_artifact(
        artifact_id="CST-9000701", interaction_id="INT-9000701", kind="colleague_statement",
        respond_by="2026-11-17T23:59:59Z", idempotency_key="REV-2026-90007:CST-9000701",
        run_id="RUN-CST", review_id="REV-2026-90007", virtual_now=datetime(2026, 11, 16, 15, tzinfo=UTC),
    )
    assert request["expected_at"] == "2026-11-17T15:00:00Z"
    release = harness.release_next("RUN-CST")
    assert release["virtual_now"] == "2026-11-17T15:00:00Z"
    assert release["arrived"] is True
    assert release["artifact"]["statement_id"] == "CST-9000701"
    assert release["artifact"]["text"] == "Customer said whatever you need to do. I explained it on the call."


def test_artifact_request_rejects_mismatched_idempotency_reuse(project_root, tmp_path):
    path = tmp_path / "run.sqlite"
    ledger = EventLedger(path, {"mode": "test"})
    harness = ArtifactHarness(project_root / "data/generated", path, ledger)
    base = {
        "artifact_id": "RTX-9000101", "interaction_id": "INT-9000101",
        "kind": "retranscription", "respond_by": "2026-11-27T23:59:59Z",
        "idempotency_key": "same", "run_id": "RUN-CONFLICT", "review_id": "REV-2026-90001",
        "virtual_now": datetime(2026, 11, 16, 15, tzinfo=UTC),
    }
    harness.request_artifact(**base)
    with pytest.raises(ValueError, match="idempotency key"):
        harness.request_artifact(**{**base, "respond_by": "2026-11-28T23:59:59Z"})
