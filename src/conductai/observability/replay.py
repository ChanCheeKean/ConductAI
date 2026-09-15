"""Ledger replay and deterministic assessment reconstruction."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from conductai.observability.events import RunEvent


def read_events(path: Path, run_id: str, *, event_type: str | None = None,
                actor: str | None = None, through_seq: int | None = None) -> list[RunEvent]:
    clauses = ["run_id=?"]
    parameters: list[Any] = [run_id]
    if event_type:
        clauses.append("type=?")
        parameters.append(event_type)
    if actor:
        clauses.append("actor_name=?")
        parameters.append(actor)
    if through_seq is not None:
        clauses.append("seq<=?")
        parameters.append(through_seq)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            f"SELECT envelope_json FROM run_events WHERE {' AND '.join(clauses)} ORDER BY seq", parameters
        ).fetchall()
    return [RunEvent.model_validate_json(row[0]) for row in rows]


def replay_assessment(path: Path, run_id: str, through_seq: int | None = None) -> dict[str, Any] | None:
    events = read_events(path, run_id, through_seq=through_seq, event_type="assessment_recorded")
    if not events:
        return None
    blob_hash = events[-1].payload["assessment_blob"]
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT redacted_bytes FROM run_blobs WHERE hash=?", (blob_hash,)).fetchone()
    return None if row is None else json.loads(row[0])
