# 03 — Data Dictionary

> Every file the generator produces, what each field means, how records join, which timestamps matter, and where the data is deliberately messy. Stage 1 implements this specification in `data/generator/` (see `handoff.md`).
> Once built: regenerate with `python3 data/generator/gen.py`; validate with `python3 data/generator/validate.py`; load with `python3 data/generator/load_sqlite.py`.

Stage 1 implementation note (2026-09-15): generation produces 6,500 non-hero interactions plus 27 hero/contact-path interactions, 53 corpus versions, 11 skills, 41,873 event rows, 6,369 document rows, 40 precedents, 58 memory notes, four harness-gated artifacts and a 10,023-node/27,259-edge graph. `load_sqlite.py` loads only agent-visible files and builds FTS5 indexes for transcript turns, corpus chunks and documents; evaluator-only `ground_truth/`, `simulation/`, `is_hero` and unreleased harness state are not loaded.

## 0. Layout and modality

```
data/
├── corpus/                              AUTHORED KNOWLEDGE (static, versioned)
│   ├── regulation/                      abridged UDAAP, Reg Z, FCRA, ECOA, SCRA, TSR text   → semantic memory
│   ├── policies/                        Copperlake SOPs and program policies               → semantic memory
│   ├── glossary/                        misconduct glossary, one file per version          → semantic memory
│   ├── scripts/                         colleague handling cards (CHC), per offer/version  → semantic memory
│   ├── products/                        product fact sheets, offer disclosures, add-on terms → semantic memory
│   ├── incentives/                      incentive plan documents                            → semantic memory
│   ├── skills/                          review playbooks                                     → procedural memory (skills)
│   └── author_corpus.py                 source of the corpus
├── generator/                           deterministic generator + validator (stdlib Python)
└── generated/                           SYNTHETIC RECORDS
    ├── structured/*.csv                 system-of-record tables                              → persistent memory (SQLite)
    ├── events/*.jsonl                   desktop, interaction and account event streams       → persistent memory (SQLite)
    ├── transcripts/<INT>.json           turn-level transcripts (ASR or exact chat/message)  → persistent + semantic
    ├── documents/crm_notes.jsonl        colleague-written notes (untrusted)                  → persistent + semantic
    ├── documents/internal_comms.jsonl   team-chat and supervisor messages                    → persistent + semantic
    ├── documents/complaints.jsonl       complaint narratives (incl. regulator-portal copies) → persistent + semantic
    ├── precedents/*.md                  adjudicated prior findings                           → semantic memory
    ├── memory_seed/                     pre-existing agent memory notes + episodic traces    → agent long-term memory
    ├── on_request/                      artifacts released only when requested (re-transcriptions, audio recovery, bureau confirmations, colleague statements) → harness-gated
    ├── simulation/                      customer personas (outreach replies)                 → harness only
    ├── reference/*.csv                  code tables, calendars, time zones, clock offsets    → tools / sandbox
    ├── graph/nodes.jsonl, edges.jsonl   relationship projection                              → graph memory
    ├── ground_truth/                    labels, reviewer baselines, sweep, capability map    → evaluator only (NEVER agent-visible)
    └── manifest.json
```

| Modality | Files | Why this modality |
|---|---|---|
| Structured tables | `structured/*.csv` | CRM, card platform, telephony and workforce systems are relational; exact joins and sums |
| Event streams | `events/*.jsonl` | Desktop activity is the screen-recording substitute; **order and timing** are the signal |
| Turn-level transcripts | `transcripts/*.json` | Word timings, speaker attribution and ASR confidence are evidence properties, not just text |
| Unstructured text | CRM notes, internal comms, complaints, precedents | Narratives, contradictions, paraphrases |
| Knowledge / policy | `corpus/**` | Versioned, cited, effective-dated rules retrieved by meaning *and* filtered by date |
| Procedural | `corpus/skills/*.md` | Review steps loaded on demand |
| Agent memory | `memory_seed/*` | What earlier reviews believed — including stale, wrong, duplicated and prohibited beliefs |
| On-request artifacts | `on_request/*` | Evidence that exists but costs time to obtain |
| Generated artifacts | *(produced at run time)* | Plans, evidence matrices, findings, assessment records, letters, memory writes — schema in §9 |

## 1. Identifiers and joins

| ID pattern | Entity | Example | Joins to |
|---|---|---|---|
| `CUS-#####` | customer (hero `CUS-9####`) | `CUS-90006` | accounts, interactions, flags, preferences, complaints |
| `ACC-#####` | card account | `ACC-90006` | cards, fee_ledger, offers, enrollments, product_changes, statements |
| `COL-####` | colleague (front-line or supervisor) | `COL-4421` | interactions, desktop_events, crm_notes, coaching_records, teams |
| `TEAM-…` | team | `T-TMP-3`, `T-SAT-2` | colleagues.team_id, teams.supervisor_id |
| `INT-#######` | interaction (hero `INT-9CCCCSS`: case number + sequence) | `INT-9000601` | transcripts, desktop_events, offers, enrollments, crm_notes, scanner_flags |
| `CBR-#######` | callback request | `CBR-9000201` | created_in_interaction_id, fulfilled_by_interaction_id |
| `OFR-…` | offer product code / offer instance | `OFR-BT-15-5`, `OFR-CLI-PS-9002201` | offers.offer_code, disclosures |
| `ENR-#######` | add-on enrollment | `ENR-9000801` | enrollments, premiums in fee_ledger |
| `PC-#######` | product change | `PC-9000701` | product_changes, rewards_ledger |
| `FLX-#######` | Flex Installments plan | `FLX-9001002` | installment_plans, fee_ledger |
| `BIR-#######` | bureau inquiry record | `BIR-9000501` | bureau_inquiries.credit_request_id |
| `COMP-#######` | complaint | `COMP-9000501` | complaints, interactions |
| `PREF-#######` | preference change | `PREF-9001801` | preferences |
| `INC-#######` | platform incident | `INC-9001801` | incidents, affected interactions |
| `CHG-…` | configuration change | `CHG-2026-1019-ASR` | config_changes |
| `SCN-…` | scanner rule / flag | `SCN-OUTBOUND-SALE` | scanner_rules, scanner_flags |
| `QAR-#######` | legacy human QA review | `QAR-0031877` | qa_reviews |
| `ICM-#######` | internal communication | `ICM-9001501` | internal_comms |
| `RTX-…`, `AUD-…`, `CST-…` | re-transcription, audio recovery, colleague statement | `RTX-9000101` | on_request/*, requested via tools |
| `REV-YYYY-#####` | review case (unit of assessment) | `REV-2026-90006` | ground_truth/cases, run outputs |
| `PRE-####` | precedent | `PRE-0022` | review_id, interaction_ids |
| `MEM-####` | agent memory note | `MEM-0350` | subject_ids, source_refs |
| `doc_id@version` | corpus document version | `CLB-GLOSS@v7`, `REGZ-1026.52@2024-03-15` | cited by findings and ground truth |

The key review path:
`interaction → transcript (turns, words, speakers) + desktop events → offers / enrollments / product changes / fee & rewards ledgers → account flags & preferences → prior interactions & callback requests (graph) → colleague history & team (graph) → script / glossary / policy / disclosure as of interaction date → precedents → memory (verified) → findings → three outcomes`.

## 2. Structured tables (`generated/structured/`)

Every table carries `is_hero` (evaluator filter; never exposed to agents) and `available_at` (UTC; harness visibility).

### customers.csv
| Field | Meaning |
|---|---|
| customer_id, first_name, last_name | fictional |
| birth_year | **prohibited for conduct decisions** (fairness trap, C14) |
| city, state, zip | home location |
| language_preference | `en` / `es` — routing signal only, never a risk signal |
| customer_since | tenure |
| trusted_contact_on_file | bool |
| military_status_on_file | `none` / `scra_active` / `scra_requested` |

### accounts.csv
`account_id, customer_id, product_code (EVERYDAY_CASH | VOYAGER | SUMMIT | FOUNDATION), opened_at, credit_limit, annual_fee, annual_fee_posting_month, statement_closing_day, status (open | closed | restricted), purchase_apr, rewards_balance, rewards_unit (cash_back | miles)`.

### account_flags.csv
`flag_id, account_id, flag (HARDSHIP_ACTIVE | SCRA_ACTIVE | DO_NOT_SOLICIT | VULNERABILITY_NOTED | FRAUD_HOLD), set_at, cleared_at, set_by_interaction_id, source_system`.

### preferences.csv
`pref_id, customer_id, preference (solicitation_opt_out | paperless | language), value, set_at, set_by_interaction_id, sync_status (synced | delayed | failed), synced_to_desktop_at`.

### colleagues.csv
`colleague_id, role (agent | supervisor), team_id, site (TEMPE | SAN_ANTONIO), site_timezone, hire_date, languages, licensed_products`. No names, demographics or performance ratings.

### teams.csv
`team_id, site, supervisor_id, queue_types`.

### interactions.csv
| Field | Meaning |
|---|---|
| interaction_id | `INT-…` |
| channel | `phone` / `chat` / `secure_message` |
| direction | `inbound` / `outbound` |
| outbound_reason | `callback` / `servicing_followup` / `none` |
| callback_request_id | set when the outbound call fulfills a CBR |
| customer_id, account_id, colleague_id | participants |
| queue | `general` / `bilingual` / `retention` / `hardship` |
| ivr_intent | caller's IVR selection (`fee_question`, `lost_card`, `close_account`, …) |
| started_at_utc, ended_at_utc | platform clock (UTC) |
| recording_status | `complete` / `partial` / `missing` (phone only) |
| recording_gaps | JSON list of `[start_offset_s, end_offset_s]` |
| asr_model | `en-US-general` / `es-US-general` / `none` (chat, secure message) |
| asr_mean_confidence | 0–1; **quality signal, never a risk signal** |
| detected_language | `en` / `es` / `mixed` |
| disposition_code | colleague-selected wrap code (`GEN_INQUIRY`, `COMPLAINT`, `SALE_ADDON`, …) |
| workstation_id | joins `reference/desktop_clock_offsets.csv` |

### callback_requests.csv
`callback_request_id, customer_id, created_in_interaction_id, created_by (colleague_id | customer_self_service), purpose (balance_transfer_offer | replacement_card_status | …), requested_window_start/end (local + tz), consent_to_call, phone, fulfilled_by_interaction_id`.

### offers.csv — presented and accepted offers
`offer_instance_id, interaction_id, account_id, offer_code, offer_type (BT | CLI | CLI_PRESCREEN | FLEX | PRODUCT_CHANGE | ADDON), presented_at_utc, eligibility_result, accepted, submitted_at_utc, amount, fee_rate, fee_amount, promo_apr, promo_months, firm_offer_valid_through, displayed_on_desktop_at_utc`.

### enrollments.csv — add-on products
`enrollment_id, account_id, product (CARDSHIELD | CREDITWATCH_PLUS), source_interaction_id, source_colleague_id, enrolled_at_local, enrolled_tz, status (active | cancelled), cancelled_at, cancel_reason, cancel_channel`. **Note:** `enrolled_at_local` + `enrolled_tz` (site clock), not UTC — deliberate (C16).

### product_changes.csv
`product_change_id, account_id, from_product, to_product, submitted_at_utc, source_interaction_id, rewards_before, rewards_after, rewards_conversion_value, benefits_removed (JSON), annual_fee_effect`.

### credit_line_requests.csv / bureau_inquiries.csv
`credit_request_id, account_id, interaction_id, requested_increase, tenure_months_at_request, policy_version_applied, decision, new_limit, income_verified, obligations_checked` · `inquiry_id, credit_request_id, inquiry_type (SOFT | HARD), bureau, pulled_at_utc, available_at`.

### installment_plans.csv
`plan_id, account_id, interaction_id, principal, months, monthly_fee_rate, monthly_fee_amount, first_fee_date, status`.

### fee_ledger.csv
`ledger_id, account_id, posted_date, type (LATE_FEE | ANNUAL_FEE | BT_FEE | ADDON_PREMIUM | PLAN_FEE | RETURNED_PAYMENT_FEE | COURTESY_WAIVER | FEE_REVERSAL | STATEMENT_CREDIT), amount, related_id, reason_code, source_interaction_id`.

### rewards_ledger.csv · statements.csv · payments.csv
Standard: `rewards_txn_id, account_id, posted_date, type, amount, unit, related_id` · `statement_id, account_id, period_start, period_end, ending_balance, transmitted_at` · `payment_id, account_id, amount, initiated_at, status (posted | returned), return_code (R01 …)`.

### complaints.csv
`complaint_id, customer_id, received_at, channel (phone | secure_message | regulator_portal), logged_by (colleague_id | system), related_interaction_ids, category, status, available_at`.

### coaching_records.csv · qa_reviews.csv
`coaching_id, colleague_id, created_at, source (qa | automated_review), topic, related_interaction_id` · legacy human QA: `qa_review_id, interaction_id, reviewer_id (R-A | R-B | R-C), reviewed_at, selected_by (scanner_rule | random | complaint), verdict (no_error | misconduct), category, notes`. **Noisy labels by design.**

### scanner_rules.csv · scanner_flags.csv
`rule_id, description, rule_logic, glossary_version_basis, deployed_at` · `flag_id, interaction_id, rule_id, flagged_at, matched_text, matched_turn_id`. The legacy keyword/structured scanner — the rules-engine baseline.

### incidents.csv · config_changes.csv
`incident_id, system (recorder | pref_sync | asr_router | order_system), started_at_utc, ended_at_utc, description, affected_count` · `change_id, system, changed_at_utc, description, reverted_at_utc`.

### unapproved_material_register.csv
Empty at `AS_OF`; written by automated action `quarantine_unapproved_material`.

## 3. Event streams (`generated/events/`)

### desktop_events.jsonl — the screen-recording substitute
| Field | Meaning |
|---|---|
| event_id | `DEV-…` |
| interaction_id, colleague_id, workstation_id | context |
| ts_local, tz | **workstation clock**, local time — apply `desktop_clock_offsets` before aligning to call UTC |
| type | `profile_loaded`, `banner_displayed`, `screen_viewed`, `disclosure_panel_opened`, `offer_panel_opened`, `eligibility_checked`, `offer_submitted`, `enrollment_submitted`, `product_change_submitted`, `fee_reversal_submitted`, `note_saved`, `disposition_set`, `preference_changed`, `callback_created` |
| payload | e.g. `{banner: "HARDSHIP_PLAN_ACTIVE"}`, `{offer_code, eligibility_result}`, `{solicitation_flag: false}` |

### interaction_events.jsonl
`hold_start/hold_end, transfer, recording_paused/resumed, overtalk_segment {start_s, end_s}, call_dropped` with offsets from call start.

### account_events.jsonl
Non-interaction account changes: statement transmitted, batch preference sync results, plan fees billed, premiums billed.

## 4. Transcripts and documents

### transcripts/<INT>.json
```json
{
  "interaction_id": "INT-9000101",
  "channel": "phone",
  "source": "asr",                         // asr | chat_exact | message_exact | retranscription
  "asr_model": "en-US-general",
  "language": "en",
  "turns": [
    {"turn_id": "t14", "speaker": "customer", "speaker_confidence": 0.93,
     "speaker_channel": "customer",         // stereo channel metadata when available; may disagree with speaker
     "start_s": 391.2, "end_s": 392.4, "text": "No. I don't need that.",
     "words": [{"w": "No", "start_s": 391.2, "end_s": 391.5, "conf": 0.41}, "..."]}
  ],
  "redactions": [{"turn_id": "t03", "type": "PAN", "span": [18, 34]}]
}
```
Chat and secure messages use the same schema with `source: chat_exact`, timestamps per message, no word confidences. Redaction is applied by the generator before writing (card numbers, SSNs) to mirror a deterministic upstream redaction stage; the agent-side `emit()` redacts again.

### documents/crm_notes.jsonl
`note_id, interaction_id, colleague_id, created_at_utc, text` — colleague assertions, **untrusted** (C06, C20).

### documents/internal_comms.jsonl
`message_id, channel (team_chat | email), author_id, team_id, sent_at_utc, text, attachments` — includes ICM-9001501.

### documents/complaints.jsonl
Narrative text for `complaints.csv` rows.

## 5. Precedents (`generated/precedents/*.md`)
Front matter: `precedent_id, review_id, interaction_ids, decided_at, glossary_version, script_versions, categories, outcome {customer, colleague, control}, flawed (hidden from agent; recorded in ground truth only)`. Body: facts, evidence, reasoning, distinguishing facts. Hand-written contrast precedents: PRE-0017, PRE-0022, PRE-0031 (flawed), PRE-0044, plus 8 more.

## 6. Memory seed (`generated/memory_seed/`)

### agent_memory_notes.jsonl
| Field | Meaning |
|---|---|
| note_id | `MEM-####` |
| kind | semantic / episodic / procedural |
| scope | colleague / team / product / policy / procedure / operational |
| subject_ids | colleague IDs, document IDs, product codes |
| content | the belief |
| created_at, created_by | agent version or legacy QA |
| source_refs | interactions, findings, documents |
| confidence | 0–1 |
| status | active / superseded / retracted / archived / purged |
| valid_from, valid_to, superseded_by | valid time |
| recorded_at, invalidated_at | record time (bi-temporal) |
| tags, sensitivity | `prohibited_basis` marks content that must be purged |
| last_accessed_at, access_count | recency/frequency |

Planted note states: **valid** (~40 notes: product facts, procedure reminders and evidence-backed colleague observations that are still current, some of which cases may read and confirm), **stale by policy change** MEM-0310 (C04), MEM-0320 (C07, vacated rule); **over-generalized consolidated** MEM-0350 + raw MEM-0351–0356 (C19); **raw, never consolidated** MEM-0341–0343 (C11) and five T-SAT-2 observations (C12); **prohibited** MEM-0396 (C14); **duplicates** and **tool-timeout noise** for expiry (background).

### run_traces/*.jsonl
Episodic traces of two earlier review runs, including `human_tester_approval` steps from **before** automated governance took effect (2026-10-01). Current runs never produce them.

## 7. On-request artifacts (`generated/on_request/`) — harness-gated

| Kind | File | Released when | Delay |
|---|---|---|---|
| Re-transcription | `retranscriptions/RTX-*.json` (transcript schema, `source: retranscription`) | `request_retranscription` called | request time + 4 h (from manifest) |
| Audio recovery | `audio_recovery/AUD-*.json` `{status: recovered | unrecoverable, transcript_ref}` | `request_audio_recovery` | fixed `available_at` |
| Bureau confirmation | reflected in `bureau_inquiries.available_at` | automatic | T+2 days |
| Colleague statement | `colleague_statements/CST-*.json` | `request_colleague_statement` | +1 business day |

Tools must return `pending` with the expected availability until the harness clock passes it.

## 8. Reference data, simulation and graph

### reference/*.csv
`glossary_codes, disposition_codes, offer_codes, product_catalog, fee_schedule, bank_holidays_2026, site_timezones, desktop_clock_offsets (workstation_id, offset_seconds, measured_at), asr_models, monitoring_sla (policy_version, business_days, clock_start_rule)`.

### simulation/customer_personas.json — harness only
Per hero customer: `customer_id, disposition, reply_to_outreach {template, available_at}, disclosure_rules` (e.g. C06 wants the product restored; C15 keeps the transfer; C17 confirms closure; C18 does not remember consenting).

### graph/nodes.jsonl, edges.jsonl
`nodes`: `{node_id "Label:key", label, key, props}` · `edges`: `{src, rel, dst, props}`.

| Label | Key |
|---|---|
| Customer, Account, Colleague, Team, Site, Interaction, CallbackRequest, Offer, Enrollment, ProductChange, InstallmentPlan, Complaint, Incident, ConfigChange, InternalMessage, Document (corpus doc@version), Precedent | IDs |

| Relationship | From → To | Source |
|---|---|---|
| HOLDS | Customer → Account | accounts |
| MEMBER_OF, SUPERVISES, LOCATED_AT | Colleague → Team; Colleague → Team; Team → Site | colleagues, teams |
| PARTICIPATED{role} | Customer/Colleague → Interaction | interactions |
| ABOUT | Interaction → Account | interactions |
| NEXT_CONTACT{gap_hours} | Interaction → Interaction (same customer, chronological) | interactions |
| CREATED_IN, FULFILLED_BY | CallbackRequest → Interaction | callback_requests |
| PRESENTED_IN, ENROLLED_IN, CHANGED_IN, PLAN_CREATED_IN | Offer/Enrollment/ProductChange/InstallmentPlan → Interaction | respective tables |
| COMPLAINS_ABOUT | Complaint → Interaction | complaints |
| AFFECTED | Incident/ConfigChange → Interaction | incidents, config_changes (derived from time windows) |
| AUTHORED, SENT_TO | Colleague → InternalMessage → Team | internal_comms |
| GOVERNED_BY{as_of} | Interaction → Document | derived from effective dates |
| DECIDED | Precedent → Interaction | precedents |

No inferred edges (patterns, material usage) are shipped — those are **agent writes** (`ConductPattern`, `UnapprovedMaterial --USED_IN-->`).

## 9. Run-time artifacts the agent produces (schemas)

### Assessment record (evaluated against ground truth)
```json
{
  "review_id": "REV-2026-90007",
  "interaction_ids": ["INT-9000701"],
  "trigger": {"type": "scanner_flag | complaint | sweep_selection | lookback | random_slice", "ref": "…"},
  "route": {"route_id": "product_change_disclosure", "track": "sales | servicing | mixed", "channel": "phone",
            "language": "en", "depth": "L4", "method": "rule | llm", "confidence": 0.93},
  "findings": [{
    "finding_id": "F1", "category": "MC-08", "status": "substantiated | not_substantiated | control_gap | insufficient_evidence",
    "attributable_to": "colleague | script | system | supervisor_material | none",
    "severity": "low | medium | high", "interaction_id": "INT-9000701",
    "evidence_spans": [{"interaction_id": "INT-9000701", "turn_id": "t19", "start_s": 402.1, "end_s": 405.0,
                        "quote": "Okay, I've taken care of that for you", "verified": true}],
    "structured_evidence": [{"source": "product_changes", "id": "PC-9000701", "fact": "Voyager → Everyday Cash at 00:07:41"}],
    "policy_refs": [{"doc_id": "CLB-CHC-PC@v3", "clause": "§2.1", "verified": true}],
    "confidence": 0.88}],
  "customer_outcome": {"harm_likely": true,
    "remediation": [{"action": "reverse_product_change | restore_rewards | refund_fee | waive_annual_fee | reverse_enrollment | refund_premiums | reverse_flex_plan | reverse_upgrade | honor_cancellation_request | log_complaint | open_scra_review | correction_letter | suppress_solicitation | notify_and_offer_reversal | none",
                     "amount": "95.00", "unit": "USD | miles", "requires_customer_confirmation": true}]},
  "colleague_outcome": {"colleague_id": "COL-3141",
    "finding": "substantiated | no_adverse_finding | no_finding | coaching_only",
    "actions": ["record_colleague_finding", "assign_coaching", "enhanced_monitoring"], "aggravating_factors": []},
  "control_outcome": {"records": [{"action": "control_gap_record | script_update_request | scanner_rule_update_request | quarantine_unapproved_material | systemic_remediation_record | targeted_lookback",
                                   "subject": "…", "population": 41, "population_query_ref": "event seq"}]},
  "adjudication": {"panel_used": true, "panel_reason": "severity_high",
    "positions": [{"role": "customer_advocate | colleague_advocate | adjudicator", "summary": "…", "key_evidence": ["…"]}],
    "computed_confidence": 0.88, "confidence_components": {"verifier_pass_rate": 1.0, "citation_verification": 1.0, "evidence_coverage": 0.9, "panel_agreement": 0.67},
    "threshold": 0.75, "conservative_default_applied": false, "flip_fact": "a disclosure of the rewards impact anywhere in the recording"},
  "waits": [{"for": "CST-9000701 | persona_reply | RTX-…", "requested_at": "…", "available_at": "…", "latest_safe_decision": "2026-11-16"}],
  "memory_ops": [{"op": "write | supersede | retract | consolidate | archive | purge | skip", "note_id": "MEM-0350", "reason": "…", "source_refs": ["…"]}],
  "graph_writes": [{"node_or_edge": "ConductPattern:COL-4421", "status": "active", "evidence": ["INT-…"]}],
  "untrusted_content": [{"interaction_id": "INT-9002301", "turn_id": "t22", "kind": "monitor_directed_instruction", "handling": "quoted_not_followed"}],
  "hypotheses": [{"id": "H2", "label": "undisclosed switch", "status": "supported", "evidence_for": [], "evidence_against": []}],
  "citations": [{"doc_id": "CLB-CHC-PC@v3", "why": "product-change disclosure requirements"}],
  "follow_ups": [{"at": "2026-11-18", "action": "link_regulator_complaint"}],
  "summary_for_record": "…",
  "customer_letter": "…"
}
```
Also produced: plan and re-plans, evidence matrix (claim → source → supports/contradicts), sandbox notebooks, panel record, letters, run trace.

## 10. Ground truth (`generated/ground_truth/`) — evaluator only

### cases/<review_id>.json
`review_id, code, title, depth, as_of, interaction_ids, summary, expected {subset of assessment record}, key_facts[{id, fact, evidence}], hypotheses[], contradictions[{id, between, resolution}], pivots[], computations[{name, value, rule}], must_cite[], must_not[], memory_ops{read, write, supersede, retract, consolidate, purge, skip}, precedents{distinguish, flawed}, acceptable_alternatives, required_capabilities[{capability, necessity: primary|supporting, why, trajectory_signals[]}], deterministic_checks[{path, op, value}], rubric[], budget{expected_tool_calls, early_termination}`.

`deterministic_checks.path` uses a JSONPath-like syntax against the assessment record (`findings[?category=='MC-08'].status`); ops: eq, approx, in, contains, contains_text, not_contains, not_contains_any, set_eq.

### background_labels.jsonl
`interaction_id, gold_status, gold_categories, attributable_to, customer_harm, is_bright_line, legacy_reviews[{reviewer_id, verdict}]` — gold labels for all ~6,500 interactions; legacy reviewer labels where reviewed.

### reviewer_baseline.json
Per legacy reviewer vs gold on the reviewed subset: precision, recall, FP rate (targets ≈ R-A 79/76/8.2%, R-B 74/71/9.8%, R-C 75/77/10.3%), plus scanner baseline.

### Q01_sweep.json
`week, capacity, random_slice {seed, strata, expected_ids}, gold_positive_ids, min_recall_at_risk_ranked, required_hero_ids, prohibited_features`.

### capability_coverage.json · hero_index.json
Capability → primary/supporting cases (validator: every capability primary in ≥ 3 cases) · IDs of hand-crafted records.

## 11. Temporal dimensions

| Timestamp | Meaning | Used for |
|---|---|---|
| `AS_OF` 2026-11-16T15:00Z | simulation "now" | visibility, SLAs |
| interactions.started_at_utc / ended_at_utc | platform clock | alignment anchor |
| transcript turn `start_s` / word timings | offsets from call start | wpm, ordering, gap overlap |
| desktop_events.ts_local + tz + workstation offset | workstation clock | event-to-speech alignment (C07b) |
| enrollments.enrolled_at_local + enrolled_tz | CRM site clock | post-call enrollment (C16) |
| offers.submitted_at_utc, product_changes.submitted_at_utc | order systems | consent-before-action |
| preferences.set_at vs synced_to_desktop_at | preference propagation | C15 |
| bureau_inquiries.available_at | T+2 | late evidence (C04) |
| complaints.received_at vs available_at | when made vs when visible | C13 regulatory dates |
| corpus effective_from / effective_to / status | rule versions | as-of retrieval |
| memory valid_from/valid_to, recorded_at/invalidated_at | belief validity (bi-temporal) | supersession, retraction |
| on-request `available_at` | artifact delays | suspend/resume |
| monitoring SLA | 10 business days from interaction (or complaint receipt) under CRM-001@v5, US bank holidays excluded | latest safe decision |

## 12. Known data-quality issues (deliberate)

| Issue | Where | Why it's there |
|---|---|---|
| ASR substitutions on consent-critical words | C01, background | transcripts are claims about audio |
| Wrong-language ASR model for a window | C10 (CHG-2026-1019-ASR) | configuration drift degrades evidence for one population |
| Diarization swaps; speaker label disagrees with channel metadata | C12, ~2% of background phone turns | who said it decides the verdict |
| Recording gaps | C18, recorder incident | evidence can be missing |
| Mixed clocks: UTC platform, local CRM, skewed workstations, Arizona without DST | C07b, C16 | alignment is computation |
| CRM notes contradict transcripts | C06, C20, background | colleague records are assertions |
| Disposition codes miscoded | C13, background | complaints hide in wrap codes |
| Stale approved script | C04 | control failures look like colleague failures |
| Scanner rules on the wrong glossary version | C10, C19 | the baseline drifts too |
| Preference sync delays | C15 | systems fail between channels |
| Noisy, biased legacy QA labels | qa_reviews | ground-truth scarcity and sampling bias |
| Flawed precedents | PRE-0031, ~5% | precedent isn't truth |
| Stale, over-generalized, raw, duplicate and prohibited memory | memory_seed | memory must be governed |
| Injection text in speech and notes | C20 | monitored content is adversarial |
| Attributes that must not be used | birth_year, language_preference as risk, asr_mean_confidence as risk, site | fairness guardrails |
