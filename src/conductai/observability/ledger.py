"""Transactional hash-chained event ledger and content-addressed blobs."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from conductai.domain.models import Actor
from conductai.observability.events import EventType, RunEvent


_SECRET = re.compile(r"(?i)(sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._-]{12,})")
# Bounded by "not adjacent to a word character or hyphen" (not just \b) so a PAN-length digit run
# embedded inside a longer hyphenated token (a UUID such as a run_id/event_id) is never matched;
# a real PAN is always a standalone token bounded by quotes, spaces, or other punctuation.
_PAN = re.compile(r"(?<![\w-])(?:\d[ -]*?){13,19}(?<=\d)(?![\w-])")
_SSN = re.compile(r"(?<![\w-])\d{3}-\d{2}-\d{4}(?![\w-])")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class EventLedger:
    """The sole public event emission boundary."""

    def __init__(self, path: Path, runtime_snapshot: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._runtime = runtime_snapshot
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS run_events (
                run_id TEXT NOT NULL, seq INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE,
                review_id TEXT NOT NULL, type TEXT NOT NULL, actor_kind TEXT NOT NULL,
                actor_name TEXT NOT NULL, span_id TEXT NOT NULL, parent_span_id TEXT,
                checkpoint_id TEXT, refs_json TEXT NOT NULL, envelope_json TEXT NOT NULL,
                prev_event_hash TEXT, event_hash TEXT NOT NULL,
                PRIMARY KEY (run_id, seq)
            );
            CREATE TABLE IF NOT EXISTS run_blobs (
                hash TEXT PRIMARY KEY, media_type TEXT NOT NULL, size INTEGER NOT NULL,
                compressed INTEGER NOT NULL DEFAULT 0, redacted_bytes BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_assessments (
                run_id TEXT PRIMARY KEY, review_id TEXT NOT NULL, assessment_json TEXT NOT NULL,
                recorded_seq INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS run_selections (
                run_id TEXT PRIMARY KEY, review_id TEXT NOT NULL, selection_json TEXT NOT NULL,
                recorded_seq INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_run_events_type ON run_events(run_id, type);
            """
        )
        self._conn.commit()

    @staticmethod
    def _redact(value: Any, path: str = "payload") -> tuple[Any, list[dict[str, str]]]:
        redactions: list[dict[str, str]] = []
        if isinstance(value, BaseModel):
            return EventLedger._redact(value.model_dump(mode="json"), path)
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for key, item in value.items():
                location = f"{path}.{key}"
                if key.lower() in {"api_key", "authorization", "secret", "token"}:
                    output[key] = "[REDACTED]"
                    redactions.append({"kind": "secret", "location": location})
                else:
                    output[key], found = EventLedger._redact(item, location)
                    redactions.extend(found)
            return output, redactions
        if isinstance(value, list):
            output = []
            for index, item in enumerate(value):
                cleaned, found = EventLedger._redact(item, f"{path}[{index}]")
                output.append(cleaned)
                redactions.extend(found)
            return output, redactions
        if isinstance(value, str):
            cleaned = _SECRET.sub("[REDACTED]", value)
            if cleaned != value:
                redactions.append({"kind": "secret", "location": path})
            pan_cleaned = _PAN.sub("[REDACTED-PAN]", cleaned)
            if pan_cleaned != cleaned:
                redactions.append({"kind": "PAN", "location": path})
            ssn_cleaned = _SSN.sub("[REDACTED-SSN]", pan_cleaned)
            if ssn_cleaned != pan_cleaned:
                redactions.append({"kind": "SSN", "location": path})
            return ssn_cleaned, redactions
        return value, redactions

    def put_blob(self, value: Any, media_type: str = "application/json") -> str:
        cleaned, _ = self._redact(value)
        content = canonical_json(cleaned).encode()
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO run_blobs(hash,media_type,size,redacted_bytes) VALUES(?,?,?,?)",
                (digest, media_type, len(content), content),
            )
        return digest

    def emit(
        self, *, run_id: str, review_id: str, virtual_now: datetime, actor: Actor,
        type: EventType | str, summary: str, payload: dict[str, Any], refs: list[str] | None = None,
        span_id: str | None = None, parent_span_id: str | None = None, branch_id: str | None = None,
        checkpoint_id: str | None = None, usage: dict[str, Any] | None = None,
    ) -> RunEvent:
        cleaned, redactions = self._redact(payload)
        event_type = EventType(type)
        with self._lock, self._conn:
            prior = self._conn.execute(
                "SELECT seq,event_hash FROM run_events WHERE run_id=? ORDER BY seq DESC LIMIT 1", (run_id,)
            ).fetchone()
            seq = 1 if prior is None else int(prior["seq"]) + 1
            prev_hash = None if prior is None else prior["event_hash"]
            wall_now = datetime.now(UTC)
            base = {
                "schema_version": 1, "event_id": f"EVT-{uuid.uuid4()}", "run_id": run_id,
                "review_id": review_id, "seq": seq, "span_id": span_id or f"SPN-{uuid.uuid4()}",
                "parent_span_id": parent_span_id, "branch_id": branch_id, "checkpoint_id": checkpoint_id,
                "ts_wall": wall_now.isoformat().replace("+00:00", "Z"),
                "ts_virtual": virtual_now.isoformat().replace("+00:00", "Z"),
                "actor": actor.model_dump(mode="json"),
                "type": event_type.value, "summary": summary, "payload": cleaned, "refs": refs or [],
                "runtime": self._runtime, "usage": usage, "redactions": redactions,
                "prev_event_hash": prev_hash,
            }
            digest = f"sha256:{hashlib.sha256(canonical_json(base).encode()).hexdigest()}"
            event = RunEvent(**base, event_hash=digest)
            envelope = event.model_dump(mode="json")
            self._conn.execute(
                "INSERT INTO run_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, seq, event.event_id, review_id, event.type.value, actor.kind, actor.name,
                 event.span_id, parent_span_id, checkpoint_id, canonical_json(event.refs),
                 canonical_json(envelope), prev_hash, digest, ),
            )
        return event

    def events(self, run_id: str) -> list[RunEvent]:
        rows = self._conn.execute(
            "SELECT envelope_json FROM run_events WHERE run_id=? ORDER BY seq", (run_id,)
        ).fetchall()
        return [RunEvent.model_validate_json(row[0]) for row in rows]

    def record_assessment(self, run_id: str, review_id: str, assessment: dict[str, Any], seq: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO run_assessments VALUES(?,?,?,?)",
                (run_id, review_id, canonical_json(assessment), seq),
            )

    def assessment(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT assessment_json FROM run_assessments WHERE run_id=?", (run_id,)).fetchone()
        return None if row is None else json.loads(row[0])

    def record_selection(self, run_id: str, review_id: str, selection: dict[str, Any], seq: int) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO run_selections VALUES(?,?,?,?)",
                (run_id, review_id, canonical_json(selection), seq),
            )

    def selection(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT selection_json FROM run_selections WHERE run_id=?", (run_id,)).fetchone()
        return None if row is None else json.loads(row[0])

    def verify_chain(self, run_id: str) -> bool:
        previous: str | None = None
        for event in self.events(run_id):
            material = event.model_dump(mode="json", exclude={"event_hash"})
            expected = f"sha256:{hashlib.sha256(canonical_json(material).encode()).hexdigest()}"
            if event.prev_event_hash != previous or event.event_hash != expected:
                return False
            previous = event.event_hash
        return True
