"""Durable request/release boundary for harness-private artifacts."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from conductai.domain.models import Actor
from conductai.observability.events import EventType
from conductai.observability.ledger import EventLedger, canonical_json


_DIRECTORIES = {
    "retranscription": "retranscriptions",
    "audio_recovery": "audio_recovery",
    "colleague_statement": "colleague_statements",
}


class ArtifactHarness:
    """The only component allowed to inspect artifact schedules and release content."""

    def __init__(self, dataset_root: Path, run_database: Path, ledger: EventLedger) -> None:
        self._dataset_root = dataset_root.resolve()
        self._database = run_database.resolve()
        self._ledger = ledger
        manifest = json.loads((self._dataset_root / "manifest.json").read_text(encoding="utf-8"))
        self._schedule = {row["artifact_id"]: row for row in manifest["on_request"]}
        with sqlite3.connect(self._database) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS artifact_requests (
                    run_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    review_id TEXT NOT NULL,
                    interaction_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    expected_at TEXT NOT NULL,
                    latest_safe_decision TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    released_at TEXT,
                    PRIMARY KEY (run_id, artifact_id),
                    UNIQUE (run_id, idempotency_key)
                );
                """
            )

    def request_artifact(
        self, *, artifact_id: str, interaction_id: str, kind: str, respond_by: str,
        idempotency_key: str, run_id: str, review_id: str, virtual_now: datetime,
    ) -> dict[str, Any]:
        schedule = self._schedule.get(artifact_id)
        if schedule is None or schedule["interaction_id"] != interaction_id or schedule["kind"] != kind:
            raise LookupError("artifact is not registered for the requested interaction and kind")
        if schedule["release"] == "request_time_plus_hours":
            expected = virtual_now + timedelta(hours=int(schedule["delay_hours"]))
        elif schedule["release"] == "fixed_available_at":
            expected = _parse(schedule["available_at"])
        else:
            raise ValueError(f"unsupported release rule: {schedule['release']}")
        latest = _parse(respond_by)
        if latest < virtual_now:
            raise ValueError("artifact deadline is before the current virtual time")
        request = {
            "artifact_id": artifact_id,
            "interaction_id": interaction_id,
            "kind": kind,
            "respond_by": _iso(latest),
            "idempotency_key": idempotency_key,
        }
        with sqlite3.connect(self._database) as conn:
            prior = conn.execute(
                "SELECT request_json,expected_at FROM artifact_requests WHERE run_id=? AND idempotency_key=?",
                (run_id, idempotency_key),
            ).fetchone()
            if prior is not None:
                if json.loads(prior[0]) != request:
                    raise ValueError("idempotency key reused with different artifact request")
                return {**request, "requested_at": _iso(virtual_now),
                        "expected_at": prior[1], "status": "already_requested"}
            conn.execute(
                "INSERT INTO artifact_requests VALUES(?,?,?,?,?,?,?,?,?,?,NULL)",
                (run_id, artifact_id, review_id, interaction_id, kind, idempotency_key,
                 _iso(virtual_now), _iso(expected), _iso(latest), canonical_json(request)),
            )
        self._ledger.emit(
            run_id=run_id, review_id=review_id, virtual_now=virtual_now,
            actor=Actor(kind="harness", name="artifact_scheduler"), type=EventType.ARTIFACT_REQUESTED,
            summary=f"Registered {kind} request {artifact_id}",
            payload={**request, "expected_at": _iso(expected), "release_rule": schedule["release"]},
            refs=[artifact_id, interaction_id],
        )
        return {**request, "requested_at": _iso(virtual_now),
                "expected_at": _iso(expected), "status": "requested"}

    def release_next(self, run_id: str) -> dict[str, Any]:
        with sqlite3.connect(self._database) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM artifact_requests WHERE run_id=? AND released_at IS NULL ORDER BY expected_at,artifact_id LIMIT 1",
                (run_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"no pending artifact request for {run_id}")
            release_at = min(_parse(row["expected_at"]), _parse(row["latest_safe_decision"]))
            arrived = _parse(row["expected_at"]) <= _parse(row["latest_safe_decision"])
            artifact: dict[str, Any] | None = None
            if arrived:
                directory = _DIRECTORIES[row["kind"]]
                private_root = (self._dataset_root / "on_request").resolve()
                path = (private_root / directory / f"{row['artifact_id']}.json").resolve()
                if not path.is_relative_to(private_root):
                    raise PermissionError("artifact path escaped harness-private root")
                artifact = json.loads(path.read_text(encoding="utf-8"))
        return {
            "virtual_now": _iso(release_at),
            "artifact_id": row["artifact_id"],
            "kind": row["kind"],
            "arrived": arrived,
            "artifact": artifact,
            "latest_safe_decision": row["latest_safe_decision"],
        }

    def acknowledge_release(self, run_id: str, artifact_id: str, released_at: str) -> None:
        with sqlite3.connect(self._database) as conn:
            changed = conn.execute(
                "UPDATE artifact_requests SET released_at=? WHERE run_id=? AND artifact_id=? AND released_at IS NULL",
                (released_at, run_id, artifact_id),
            ).rowcount
        if changed != 1:
            raise RuntimeError("artifact release acknowledgement did not match one pending request")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
