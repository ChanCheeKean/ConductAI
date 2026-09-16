from datetime import UTC, datetime

from conductai.data.repository import OperationalRepository
from conductai.observability.ledger import EventLedger


def test_get_interaction_returns_full_row_for_c18_recording_gap(project_root, tmp_path):
    ledger = EventLedger(tmp_path / "run.sqlite", {"mode": "test"})
    repository = OperationalRepository(project_root / "data/generated/conduct.sqlite", ledger)
    row = repository.interaction(
        "INT-9002101", run_id="RUN-TEST", review_id="REV-2026-90021",
        virtual_now=datetime(2026, 11, 16, 15, tzinfo=UTC),
    )
    assert row["recording_status"] == "partial"
    assert row["recording_gaps"] == "[[252,400]]"
    assert row["disposition_code"] == "SALE_ADDON"
