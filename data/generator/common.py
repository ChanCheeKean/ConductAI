"""Shared primitives for the ConductAI synthetic data generator.

Deterministic given SEED. Standard library only (Python 3.9+).
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import random
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

SEED = 20261116
UTC = dt.timezone.utc

# Simulation clock: Monday 2026-11-16 09:00 America/Chicago.
AS_OF = dt.datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
AS_OF_ISO = "2026-11-16T15:00:00Z"
AS_OF_DATE = "2026-11-16"
HISTORY_START = "2026-08-17"   # first background interaction date
HISTORY_END = "2026-11-13"     # last background interaction date (Friday before AS_OF)

GEN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# CONDUCT_OUT lets parallel development runs write somewhere other than data/generated.
OUT_DIR = os.environ.get("CONDUCT_OUT") or os.path.join(GEN_ROOT, "generated")
CORPUS_DIR = os.path.join(GEN_ROOT, "corpus")

HIDDEN_COLUMNS = ("is_hero",)  # evaluator-only; stripped from every agent-visible file


# ---------------------------------------------------------------- money
def money(x) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def m(x) -> str:
    """Money as a 2-decimal string."""
    return str(money(x))


# ---------------------------------------------------------------- time
def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def parse_utc(s: str) -> dt.datetime:
    """'2026-11-10T21:15:00Z' -> aware UTC datetime."""
    return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def iso_utc(x: dt.datetime) -> str:
    return x.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_to_utc(date_s: str, time_s: str, tz: str) -> str:
    """Local wall time in `tz` -> ISO UTC string."""
    naive = dt.datetime.fromisoformat(f"{date_s}T{time_s}")
    return iso_utc(naive.replace(tzinfo=ZoneInfo(tz)))


def utc_to_local(ts_utc: str, tz: str) -> str:
    """ISO UTC -> local wall time 'YYYY-MM-DDTHH:MM:SS' (no offset)."""
    return parse_utc(ts_utc).astimezone(ZoneInfo(tz)).strftime("%Y-%m-%dT%H:%M:%S")


def add_seconds(ts_utc: str, seconds: float) -> str:
    return iso_utc(parse_utc(ts_utc) + dt.timedelta(seconds=round(seconds)))


def add_days(date_s: str, n: int) -> str:
    return (d(date_s) + dt.timedelta(days=n)).isoformat()


def stable_hex(*parts, n: int = 12) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:n]


def sub_rng(*parts) -> random.Random:
    """Independent deterministic RNG for one record family, so adding records elsewhere never shifts it."""
    return random.Random(int(stable_hex(SEED, *parts, n=16), 16))


# ---------------------------------------------------------------- schemas
# Column order for every table. `available_at` (UTC) gates harness visibility; `is_hero` is evaluator-only.
_TAIL = ["available_at", "is_hero"]
STRUCTURED = {
    "customers": ["customer_id", "first_name", "last_name", "birth_year", "city", "state", "zip", "email", "phone",
                  "language_preference", "customer_since", "trusted_contact_on_file", "military_status_on_file"],
    "accounts": ["account_id", "customer_id", "product_code", "opened_at", "credit_limit", "annual_fee",
                 "annual_fee_posting_month", "statement_closing_day", "status", "purchase_apr", "rewards_balance",
                 "rewards_unit"],
    "account_flags": ["flag_id", "account_id", "flag", "set_at", "cleared_at", "set_by_interaction_id", "source_system"],
    "preferences": ["pref_id", "customer_id", "preference", "value", "set_at", "set_by_interaction_id", "sync_status",
                    "synced_to_desktop_at"],
    "colleagues": ["colleague_id", "role", "team_id", "site", "site_timezone", "hire_date", "languages",
                   "licensed_products"],
    "teams": ["team_id", "site", "supervisor_id", "queue_types"],
    "interactions": ["interaction_id", "channel", "direction", "outbound_reason", "callback_request_id", "customer_id",
                     "account_id", "colleague_id", "queue", "ivr_intent", "started_at_utc", "ended_at_utc",
                     "recording_status", "recording_gaps", "asr_model", "asr_mean_confidence", "detected_language",
                     "disposition_code", "workstation_id"],
    "callback_requests": ["callback_request_id", "customer_id", "created_in_interaction_id", "created_by", "purpose",
                          "requested_window_start", "requested_window_end", "requested_tz", "consent_to_call", "phone",
                          "fulfilled_by_interaction_id"],
    "offers": ["offer_instance_id", "interaction_id", "account_id", "offer_code", "offer_type", "presented_at_utc",
               "eligibility_result", "accepted", "submitted_at_utc", "amount", "fee_rate", "fee_amount", "promo_apr",
               "promo_months", "firm_offer_valid_through", "displayed_on_desktop_at_utc"],
    "enrollments": ["enrollment_id", "account_id", "product", "source_interaction_id", "source_colleague_id",
                    "enrolled_at_local", "enrolled_tz", "status", "cancelled_at", "cancel_reason", "cancel_channel"],
    "product_changes": ["product_change_id", "account_id", "from_product", "to_product", "submitted_at_utc",
                        "source_interaction_id", "rewards_before", "rewards_after", "rewards_conversion_value",
                        "benefits_removed", "annual_fee_effect"],
    "credit_line_requests": ["credit_request_id", "account_id", "interaction_id", "requested_at_utc",
                             "requested_increase", "tenure_months_at_request", "policy_version_applied", "decision",
                             "new_limit", "income_verified", "obligations_checked"],
    "bureau_inquiries": ["inquiry_id", "credit_request_id", "account_id", "inquiry_type", "bureau", "pulled_at_utc"],
    "installment_plans": ["plan_id", "account_id", "interaction_id", "principal", "months", "monthly_fee_rate",
                          "monthly_fee_amount", "first_fee_date", "status"],
    "fee_ledger": ["ledger_id", "account_id", "posted_date", "type", "amount", "related_id", "reason_code",
                   "source_interaction_id"],
    "rewards_ledger": ["rewards_txn_id", "account_id", "posted_date", "type", "amount", "unit", "related_id"],
    "statements": ["statement_id", "account_id", "period_start", "period_end", "ending_balance", "transmitted_at"],
    "payments": ["payment_id", "account_id", "amount", "initiated_at", "status", "return_code"],
    "complaints": ["complaint_id", "customer_id", "received_at", "channel", "logged_by", "related_interaction_ids",
                   "category", "status"],
    "coaching_records": ["coaching_id", "colleague_id", "created_at", "source", "topic", "related_interaction_id"],
    "qa_reviews": ["qa_review_id", "interaction_id", "reviewer_id", "reviewed_at", "selected_by", "verdict",
                   "category", "notes"],
    "scanner_rules": ["rule_id", "description", "rule_logic", "glossary_version_basis", "deployed_at"],
    "scanner_flags": ["flag_id", "interaction_id", "rule_id", "flagged_at", "matched_text", "matched_turn_id"],
    "incidents": ["incident_id", "system", "started_at_utc", "ended_at_utc", "description", "affected_count"],
    "config_changes": ["change_id", "system", "changed_at_utc", "description", "reverted_at_utc"],
    "unapproved_material_register": ["material_id", "message_id", "quarantined_at", "reason"],
}
EVENTS = {
    "desktop_events": ["event_id", "interaction_id", "colleague_id", "workstation_id", "ts_local", "tz", "type",
                       "payload"],
    "interaction_events": ["event_id", "interaction_id", "type", "offset_s", "end_offset_s", "detail"],
    "account_events": ["event_id", "account_id", "type", "ts_utc", "detail"],
}
DOCUMENTS = {
    "crm_notes": ["note_id", "interaction_id", "colleague_id", "created_at_utc", "text"],
    "internal_comms": ["message_id", "channel", "author_id", "team_id", "sent_at_utc", "text", "attachments"],
    "complaint_narratives": ["complaint_id", "received_at", "channel", "text"],
}
SCHEMAS = {k: v + _TAIL for group in (STRUCTURED, EVENTS, DOCUMENTS) for k, v in group.items()}
# Sort key per table for byte-stable output (first column unless listed).
SORT_KEYS = {
    "desktop_events": ("interaction_id", "event_id"),
    "interaction_events": ("interaction_id", "event_id"),
    "account_events": ("ts_utc", "event_id"),
}


class Ctx:
    """In-memory store of every generated record."""

    def __init__(self, seed: int = SEED):
        self.rng = random.Random(seed)
        self.t = defaultdict(list)            # table -> rows
        self.index = defaultdict(dict)        # table -> primary key -> row
        self.counters = defaultdict(int)
        self.transcripts = {}                 # interaction_id -> transcript dict
        self.on_request = defaultdict(dict)   # kind (retranscriptions|audio_recovery|colleague_statements) -> id -> dict
        self.on_request_log = []              # manifest entries {artifact_id, kind, interaction_id, delay, available_at}
        self.personas = {}                    # customer_id -> persona dict
        self.precedents = {}                  # precedent_id -> {"meta": dict, "body": str}
        self.memory_notes = []
        self.run_traces = {}                  # trace_id -> list of steps
        self.ground_truth = {}                # review_id -> dict
        self.bg_labels = {}                   # interaction_id -> gold label dict
        self.planted = {}                     # structure name -> facts recorded for ground truth / validation
        self.q01 = {}

    # ids
    def next_id(self, prefix: str, width: int = 7) -> str:
        self.counters[prefix] += 1
        return f"{prefix}-{self.counters[prefix]:0{width}d}"

    def add(self, table: str, row: dict) -> dict:
        cols = SCHEMAS[table]
        unknown = set(row) - set(cols)
        if unknown:
            raise KeyError(f"{table}: unknown columns {sorted(unknown)}")
        full = {c: row.get(c, "") for c in cols}
        if full["is_hero"] == "":
            full["is_hero"] = False
        key = full[cols[0]]
        if key in self.index[table]:
            raise KeyError(f"{table}: duplicate key {key}")
        self.t[table].append(full)
        self.index[table][key] = full
        return full

    def get(self, table: str, key: str) -> dict:
        return self.index[table][key]

    def has(self, table: str, key: str) -> bool:
        return key in self.index[table]


# ---------------------------------------------------------------- writers
def cell(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    if v is None:
        return ""
    return v


def visible(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in HIDDEN_COLUMNS}


def sorted_rows(table: str, rows: list) -> list:
    keys = SORT_KEYS.get(table, (SCHEMAS[table][0],))
    return sorted(rows, key=lambda r: tuple(str(r[k]) for k in keys))


def write_csv(path: str, cols: list, rows: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([cell(r[c]) for c in cols])


def write_jsonl(path: str, rows: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n")


def write_json(path: str, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def write_text(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
