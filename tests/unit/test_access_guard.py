from datetime import UTC, datetime

import pytest

from conductai.data.repository import AccessDenied, OperationalRepository
from conductai.observability.ledger import EventLedger


@pytest.mark.parametrize("resource", ["ground_truth/cases/x.json", "simulation/personas.json", "on_request/x.json", "field:is_hero"])
def test_restricted_resources_are_denied_and_logged(project_root, tmp_path, resource):
    ledger = EventLedger(tmp_path / "run.sqlite", {"model": "fake"})
    repository = OperationalRepository(project_root / "data/generated/conduct.sqlite", ledger)
    with pytest.raises(AccessDenied):
        repository.guard_resource(resource, run_id="RUN-1", review_id="REV-1", virtual_now=datetime.now(UTC))
    assert ledger.events("RUN-1")[-1].type.value == "access_denied"
