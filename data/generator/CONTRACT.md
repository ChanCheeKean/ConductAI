# Generator contract

Decisions every generator module relies on. The case catalog (`docs/design/02-case-catalog.md`) is the narrative contract; this file pins the implementation choices the catalog leaves open. Change a line here only together with every module that depends on it, and record the change in `handoff.md`.

## 1. Pipeline and module ownership

`gen.py` runs: `world.build` → `people.build` → `heroes.cases_a..e.build` → `background.build` → `oversight.build` → `precedents.build` → `memory_seed.build` → `sweep.build` → `graph.build`, then every module's optional `finalize(ctx)` in the same order, then writes.

| Module | Owns |
|---|---|
| `common.py`, `derived.py`, `world.py`, `records.py`, `transcripts.py`, `people.py`, `heroes/kit.py`, `capabilities.py`, `gen.py` | foundation (main session) |
| `heroes/cases_a.py` | C01, C02, C02b, C03, **C04 + its 46-call population** |
| `heroes/cases_b.py` | C05, C06, C07, C07b, C08, C09 |
| `heroes/cases_c.py` | **C10 + 62 other ASR-window calls**, **C11 + COL-4421's other 22 enrollment calls**, **C11b + COL-4425's other 18 enrollment calls** |
| `heroes/cases_d.py` | **C12 + 16 other phrase segments + ICM-9001501**, C13, C14, **C15 + preference-sync incident population** |
| `heroes/cases_e.py` | **C16 + COL-3122's 6 post-call enrollments**, C17, **C18 + recorder-failover population**, C19, C20 |
| `background.py`, `asr_noise.py` (+ template grammar) | all other interactions, transcripts, events, ledgers, notes, comms, complaints, gold positives |
| `oversight.py` | scanner rules + flags for non-authored interactions, legacy QA reviews, coaching records, reviewer baseline |
| `precedents.py`, `memory_seed.py` | precedents, memory notes, run traces |
| `sweep.py`, `graph.py`, `validate.py`, `load_sqlite.py` | Q01 ground truth, graph projection, validation, SQLite |

## 2. IDs

- Hero customers/accounts: `CUS-9XXXX` / `ACC-9XXXX` where XXXX is the review number (C01 → `CUS-90001`, C18 → `CUS-90021`). A second hero customer in the same case: `CUS-9XXXX` is taken, so use `CUS-95XXX` style (`CUS-95012`).
- Hero interactions `INT-9CCCCSS` (catalog). Other hero records use the same 7-digit stem: `ENR-9000101`, `PC-9000701`, `FLX-9001002`, `CRQ-9000401` (credit request), `BIR-…`, `FEE-9000801-01`, `RWD-9000701-01`, `PAY-9001601-01`, `FLG-9001001`, `PREF-9001801`, `COACH-…`, `STM-<acct digits>-<YYYYMM>`.
- **Population members that the catalog does not name** use background-range opaque IDs from `records.opaque_id(ctx, "INT", "interactions", "<case>", i)` (and the same helper with the relevant prefix/table for their ENR/CRQ/BIR/FEE rows), draw customers from `people.pick`, and have `is_hero=False`. Named population members (e.g. `INT-9001509`, `INT-9001514`) keep catalog IDs and `is_hero=True`.
- Desktop events `DEV-<stem>-NN`, interaction events `IEV-<stem>-NN`, scanner flags `SFL-<stem>-NN`, CRM notes `NOTE-<stem>` are assigned by `records.py`.
- Known leakage caveat: named hero IDs are in the 9-range by catalog design; unnamed population members are not, so populations must be found by query.

## 3. Clocks

- `AS_OF` 2026-11-16T15:00:00Z. No agent-visible record may have `available_at` > AS_OF unless the catalog makes it late (bureau inquiries T+2, regulator-portal complaint, re-transcriptions/audio/statements via on_request, persona replies).
- Background interaction dates 2026-08-17 → 2026-11-13. Contact centers are open on bank holidays (Labor Day, Columbus Day, Veterans Day) at reduced volume (40%); closed Thanksgiving (outside range). Weekend volume 25% of a weekday.
- Tempe = America/Phoenix (no DST); San Antonio = America/Chicago. Customer-facing times in the catalog marked CT/MST are converted with `common.local_to_utc`.
- Legacy human QA reviews (`qa_reviews.reviewed_at`) are all **before 2026-10-01** (automated governance starts then).

## 4. Population and quota decisions (background must respect them)

| Structure | Decision |
|---|---|
| C04 CLI population | Interactions on/after 2026-10-01 with a credit-line request that produced a **HARD** inquiry: exactly 47 = 41 affected (incl. hero INT-9000501; 38 with the exact CHC-CLI@v4 sentence incl. hero, 3 paraphrased) + 6 where the colleague correctly warned of a hard inquiry. **Background creates only SOFT-inquiry CLI requests** (tenure ≥ 12 months and increase ≤ $5,000 on/after 10-01; any before 10-01). Background CLI calls may read the script sentence (it is accurate on soft pulls). |
| C10 ASR window | `CHG-2026-1019-ASR` changed 2026-10-19T13:00:00Z, reverted 2026-11-06T18:00:00Z. Exactly 63 bilingual-queue phone calls start inside the window (incl. hero INT-9001201), all `asr_model=en-US-general`. **Background creates no bilingual-queue calls inside the window.** Outside it, bilingual calls with Spanish/mixed speech use `es-US-general`. |
| C11 COL-4421 | Exactly 23 CardShield enrollments by COL-4421 between 2026-09-01 and 2026-11-13 (incl. hero INT-9001301 trigger): 15 without affirmative consent (incl. trigger), 6 explicit informed consent, 2 with recording gaps over the consent moment. 14 cancelled within 30 days of enrollment (trigger cancelled 2026-11-10 by its complaint); 4 complaints (incl. COMP-9001301). **Background creates no add-on enrollments for COL-4421 or COL-4425.** |
| C11b COL-4425 | Exactly 19 CardShield enrollments 2026-09-01 → 11-13 (incl. hero INT-9001401), all explicit consent; 2 cancelled within 30 days; 0 complaints. |
| Program early-cancel stats | Rate = CardShield enrollments cancelled within 30 days / CardShield enrollments, per colleague, window 2026-09-01 → 11-13. Among colleagues with ≥ 10 such enrollments, COL-4421 is highest and COL-4425 is within one population standard deviation of the mean (`derived.colleague_cancel_stats`). Background targets: program rate ≈ 11%; T-TMP-3 median ≈ 6 enrollments per agent; ~8–12 colleagues with ≥ 10. |
| C12 cheat sheet | ICM-9001501 sent 2026-10-02 by COL-6600. 17 interactions on/after 2026-10-05 by 5 T-SAT-2 colleagues (COL-6630 + 4 others) contain a semantically similar segment (incl. hero chat INT-9001501); 2 are not misrepresentations (INT-9001509 diarization swap, INT-9001514 negation) → 15 affected customers. The exact phrase "basically free" occurs in exactly 3 of the 17 transcripts. **Background never says CardShield (or any product) is free / costs nothing / only charged if you carry a balance.** |
| C15 preference sync | `INC-9001801` pref_sync 2026-10-12T15:30:00Z → 2026-10-20T22:00:00Z, `affected_count` 1214 (bank-wide). In the dataset, every preference change set inside the window has `sync_status=delayed` and `synced_to_desktop_at` after the incident end; cases_d owns all of them (~60–90 rows, ≥ 30 solicitation opt-outs). Exactly 9 dataset customers with a delayed solicitation opt-out received a sales offer on an interaction during their delay (incl. hero INT-9001802). **Background creates no preference rows inside the window and never presents offers to customers with a solicitation opt-out.** |
| C16 post-call | COL-3122 has exactly 6 other CreditWatch Plus enrollments submitted 1–5 minutes after their call ended, 2026-10-10 → 11-09 (5 never activated monitoring: `account_events` type `creditwatch_activated` absent). **Background enrollments are always submitted during the call.** |
| C18 recorder failover | `INC-9002101` recorder 2026-11-11 13:50–14:20 CT, `affected_count` 23. Exactly 23 phone calls overlap the window, each `recording_status=partial` with a gap inside it (incl. hero INT-9002101); exactly 4 have an `enrollment_submitted` or `offer_submitted` desktop event inside the gap (incl. hero). **Background creates no phone calls overlapping 2026-11-11 13:40–14:30 CT** and gives recording gaps to at most 0.3% of other calls. |
| Q01 week | 2026-11-09 → 11-13, ≈ 500 interactions incl. heroes. |

Planted modules record their populations in `ctx.planted["<case>"]` (interaction IDs, counts, customer IDs, amounts) and list every interaction whose scanner flags they authored in `ctx.planted.setdefault("scanner_authored", [])`.

## 5. Scanner rules (14; `oversight.py` authors the table; heroes add catalog flags explicitly)

`SCN-CONSENT-NEG-ENROLL`, `SCN-OUTBOUND-SALE`, `SCN-CREDIT-ASSURANCE`, `SCN-WAIVER-ENROLL-60S`, `SCN-NO-FEE-DISCLOSED`, `SCN-NO-INTEREST-FRAMING`, `SCN-TOPDECILE-ADDON-TEAMFLAG`, `SCN-PREAPPROVED`, `SCN-SOLICIT-AFTER-OPTOUT`, `SCN-CREDIT-SCORE-PHRASE`, `SCN-FREE-CLAIM`, `SCN-REQUIRED-ADDON`, `SCN-GUARANTEED`, `SCN-CANCEL-REBUTTAL-3X`. `oversight.py` applies rules only to interactions that are not `is_hero` and not in `planted["scanner_authored"]`.

## 6. Gold labels

`kit.label(ctx, interaction_id, gold_status, categories, attributable_to=…, customer_harm=…, is_bright_line=…, source=…)` for **every** interaction (heroes and populations label their own; background/oversight label the rest). `gold_status ∈ no_error | misconduct | control_gap | insufficient_evidence`. Prevalence target: `misconduct` = 3.6% ± 0.2% of non-hero interactions (planted positives count toward it).

## 7. Memory notes and precedents referenced by cases (`memory_seed.py`, `precedents.py`)

- `MEM-0310` (C04 stale CLI), `MEM-0320` (C07 vacated late-fee cap), `MEM-0341`–`MEM-0343` (raw 2026-08 QA observations about COL-4421, scoped to COL-4421; also the notes C11b must reject for COL-4425), `MEM-0350` consolidated + `MEM-0351`–`MEM-0356` raw (C19), `MEM-0361`–`MEM-0365` raw T-SAT-2 observations (C12), `MEM-0396` prohibited (C14). Other notes use `MEM-0001…0299` and `MEM-0400+`.
- Precedents `PRE-0017` (general utilization statement → no_error), `PRE-0022` (3% said on a genuine 3% offer under CHC-BT@v4 → no_error), `PRE-0031` (flawed SCRA), `PRE-0044` (cancellation not processed → MC-06), plus 8 more hand-written and templated to ~40 total, ~5% flawed.

## 8. Personas and on-request artifacts

- Personas keyed by customer: CUS-90007 (C06), CUS-90018 (C15), CUS-90020 (C17), CUS-90021 (C18), with reply `available_at` from the catalog.
- `RTX-9000101` (C01), `RTX-9001201` (C10): release = request time + 4 h. `CST-9000701` (C06): request time + 1 business day. `AUD-9002101` (C18): fixed `available_at` 2026-11-16T22:00:00Z.
