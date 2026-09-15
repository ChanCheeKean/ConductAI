"""Frontend-facing JSON Schema exports."""

from __future__ import annotations

import json
from pathlib import Path

from conductai.domain.models import AssessmentRecord
from conductai.observability.events import EventType, RunEvent


def export_schemas(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    event_schema = RunEvent.model_json_schema()
    event_schema["$comment"] = "payload is discriminated by the complete event_types enumeration"
    event_schema["event_types"] = [event.value for event in EventType]
    (directory / "run-event-v1.schema.json").write_text(json.dumps(event_schema, indent=2) + "\n", encoding="utf-8")
    (directory / "assessment-record-v1.schema.json").write_text(
        json.dumps(AssessmentRecord.model_json_schema(), indent=2) + "\n", encoding="utf-8"
    )
