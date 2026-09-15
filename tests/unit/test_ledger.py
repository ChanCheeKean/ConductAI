from datetime import UTC, datetime

from conductai.domain.models import Actor
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger


def test_ledger_redacts_and_verifies_hash_chain(tmp_path):
    ledger = EventLedger(tmp_path / "run.sqlite", {"model": "fake"})
    event = ledger.emit(
        run_id="RUN-1", review_id="REV-1", virtual_now=datetime.now(UTC),
        actor=Actor(kind="runtime", name="test"), type=EventType.RUN_STARTED,
        summary="test", payload={"api_key": "sk-abcdefghijklmnop", "pan": "4111 1111 1111 1111"},
    )
    assert event.payload["api_key"] == "[REDACTED]"
    assert event.payload["pan"] == "[REDACTED-PAN]"
    assert {item["kind"] for item in event.redactions} == {"secret", "PAN"}
    assert ledger.verify_chain("RUN-1")
