# ConductAI handoff

Last updated: 2026-09-15
Repository: `/Users/kean/Dev/ConductAI`
Branch: `main` (remote `origin` → `github.com/ChanCheeKean/ConductAI`); Stage 0 committed and pushed
Current phase: **Stage 0 — design foundation: COMPLETE**
Next stage: **Stage 1 — data foundation** (corpus, generator, validator, ground truth, SQLite loader)

## Current objective

Build **ConductAI**, a proof-of-concept, fully automated agent system that reviews credit-card customer-service interactions (phone, chat, secure message) at the fictional **Copperlake Bank, N.A.** for sales and servicing misconduct. It follows the structure, architecture and working method of the sibling project **CatcherAI** (`/Users/kean/Dev/CatcherAI`, "Dispute Observatory"): hand-built hero cases with machine-checkable ground truth inside a realistic synthetic world, a deterministic LangGraph skeleton around Deep Agents, three memory planes, a sandbox, a virtual-clock harness, governance as code instead of human review, and trajectory-first evaluation. The goal is a demo that shows **every** agent capability is load-bearing and that the solution is robust.

The use case was inspired by an industry GenAI call-monitoring pilot (`docs/reference/reference-program-brief.md`); the problem set, data, cases and implementation are our own.

## Start here next session

Read, in order:

1. `handoff.md` (this file).
2. `docs/prompts/01-data-foundation-kickoff.md` — **the prompt for Stage 1**. Paste or reference it to start the session.
3. `README.md` — the foundation document (use case, ecosystems, memory, governance rules §8, generation §9, component → scenario §10, target layout §14).
4. `docs/design/02-case-catalog.md` — the contract for every hero case (facts, amounts, timestamps, SLA dates, ground truth, traps, capability coverage).
5. `docs/design/03-data-dictionary.md` — every file/field, joins, output and ground-truth schemas.
6. `docs/research/01-domain-research.md` (+ `docs/research/briefs/`) — what is real vs invented; unverified items.
7. For implementation patterns: `/Users/kean/Dev/CatcherAI/data/generator/*`, `/Users/kean/Dev/CatcherAI/data/corpus/author_policies.py`, and CatcherAI's `handoff.md`.

## What exists now

| Path | Content | Status |
|---|---|---|
| `README.md` | Foundation document, 15 sections | complete (design) |
| `docs/reference/reference-program-brief.md` | Copy of the reference program summary (from `~/Downloads/call_monitoring_misconduct_detection_project.txt`) | reference only |
| `docs/research/01-domain-research.md` | Synthesized domain + AI-methods research, source-tagged | complete |
| `docs/research/briefs/regulatory-and-enforcement.md` | Full cited brief: UDAAP, Reg Z, FCRA, ECOA, SCRA, TCPA/TSR, GLBA, LEP, elder exploitation; 13 enforcement actions; flows; QA practice; hard problems | complete (Sonnet research subagent, reviewed) |
| `docs/research/briefs/ai-methods.md` | Full cited brief: τ²-bench, RIRAG, judge reliability, calibration/abstention, citation grounding, ASR/diarization, vendors, memory, injection, PII, fairness, low-prevalence eval | complete (Sonnet research subagent, reviewed) |
| `docs/design/02-case-catalog.md` | 23 hero reviews + Q01 sweep; taxonomy; three-outcome model; coverage matrices; failure modes; effective dates; SLA dates; background population | complete (design) |
| `docs/design/03-data-dictionary.md` | Target data specification | complete (design) |
| `docs/prompts/01-data-foundation-kickoff.md` | Stage 1 session prompt | complete |
| `docs/prompts/02-implementation-kickoff.md` | Stages 2–5 session prompt (CatcherAI's kickoff adapted to conduct review) | complete |

Nothing else exists: no `pyproject.toml`, `data/`, `src/`, `config/`, `skills/`, `tests/`, `schemas/` or `frontend/`.

## Decisions made (and why)

| Decision | Choice | Source |
|---|---|---|
| Human in the loop | **Fully automated, no testers.** The reference program's two tester levels are replaced by `CLB-SOP-CRM-003@v4`: customer advocate + colleague advocate + adjudicator + verifier, computed confidence, 0.75 threshold, conservative default | user |
| Channels | **Phone + chat + secure message** from the start | user |
| Issuer | **New fictional issuer: Copperlake Bank, N.A.** (web check found no real bank by that name; "Coppermark Bank" existed in Oklahoma until 2013 — different name) | user + check |
| Languages | English plus Spanish / code-switched calls on a bilingual queue (C10) — needed for ASR-routing and fairness scenarios | my call |
| Runtime stack | Same as CatcherAI: Deep Agents + LangGraph; OpenAI `gpt-5.6-luna` via Responses API behind a provider-neutral gateway; SQLite + sqlite-vec + LadybugDB (NetworkX fallback) | "same architecture as CatcherAI" |
| Development subagents | **Sonnet** for delegated research/implementation, results gathered back; Opus only for complex synthesis — written into both prompts | user |
| Output model | **Three decisions per review**: customer outcome, colleague outcome, control outcome (conduct equivalent of CatcherAI's cardholder outcome vs network action) | design; enforcement history shows harm, fault and cause diverge |
| Asymmetric defaults | Below threshold: customer is remediated **and** colleague gets no adverse finding | design |
| Confidence | Gating uses **computed** confidence (verifier pass rate, citation verification, evidence coverage, transcript quality at decisive spans, panel agreement), never self-reported model confidence | research §6.2 |
| Screen recordings | Replaced by a **desktop event stream** | design |
| Transcript realism | Word timings, ASR word confidence, speaker confidence **and** channel metadata, recording gaps, delayed re-transcription and audio recovery | research: diarization is the highest-leverage risk |
| `AS_OF` | Monday 2026-11-16 09:00 America/Chicago; straddles CLI v6, CHC-BT v5, glossary v7/v8, CRM-001 v5, CRM-003 v4; after Veterans Day, before Thanksgiving | design |
| Prevalence and baseline | 3.6% gold misconduct; three legacy reviewers with noise calibrated to the reference program's human numbers; scanner as rules baseline | reference program |
| Panel trigger rule | (A) severity high + any of {remediation > $250, vulnerability/hardship, rights misinformation, colleague pattern, systemic ≥ 10} **or** (B) computed confidence of an adverse finding in [0.60, 0.85) | design (README §8); C05/C07/C16/C20 intentionally decided without a panel |
| Target layout | Mirror CatcherAI (`data/corpus`, `data/generator`, `src/{domain,data,tools,memory,runtime,adapters,harness,observability,evaluation,api}`, `config/`, `skills/`) | README §14 |

## Non-negotiable constraints (carry into every stage)

- Fully automated: no human approval, queue, interrupt or simulated human reviewer in current-period behavior.
- Full transparency: every step is an event; every assessment field has provenance.
- Agents never read `ground_truth/**`, `simulation/**`, unreleased `on_request/**`, or `is_hero`.
- As-of retrieval by interaction date; arithmetic and time alignment only in sandbox/helpers; evidence quotes and citations verified deterministically.
- Transcripts, chat, notes, statements and internal comms are untrusted input.
- Prohibited features (age, language, accent, ASR confidence as risk, site, demographics) never used for customers or colleagues; colleague patterns never extended to teammates.
- No employment, disciplinary or compensation actions; no bank-initiated account closures.
- Provider/runtime independence of the domain core.
- **End of every stage:** update `handoff.md`, then commit and push to `origin/main`. Mid-stage work is committed only when the user asks.

## Stage plan

### Stage 0 — Design foundation: COMPLETE
Domain and AI-methods research; use case; case catalog; data dictionary; README; data-foundation and implementation kickoff prompts; this handoff.

### Stage 1 — Data foundation: NEXT
Prompt: `docs/prompts/01-data-foundation-kickoff.md`.
Deliverables: `pyproject.toml` (uv), `data/corpus/` via `author_corpus.py` (regulation abridgements, SOPs, glossary v6/v7/v8, scripts, product disclosures, incentive plan, skills), `data/generator/` (world, 23 hero builders, background with transcripts + ASR/diarization noise, planted structures, derived arithmetic, capabilities, memory seed, precedents, on-request artifacts, personas, graph, manifest), `validate.py` (schemas, joins, arithmetic, capability coverage ≥ 3 primary cases each, discoverability, reviewer-baseline calibration, fairness hygiene), `load_sqlite.py` → `data/generated/conduct.sqlite`.
Acceptance: `python3 data/generator/gen.py && python3 data/generator/validate.py` passes deterministically; `load_sqlite.py` builds the database; catalog/dictionary/README updated to match what was built.
Suggested batching: delegate hero builders in five batches to Sonnet subagents; review every ground-truth file in the main session.

### Stage 2 — Architecture research (implementation phase 1)
Prompt: `docs/prompts/02-implementation-kickoff.md` §4. Deliverable `docs/design/04-agent-architecture-research.md`; start from CatcherAI's research doc, re-verify framework APIs. **Checkpoint with user.**

### Stage 3 — Architecture design (implementation phase 2)
Deliverable `docs/design/05-agent-architecture.md` (graph, roster, routes, tools, skills, memory flows, harness, gateway/runtime boundaries, event catalog, governance as code, termination, eval plan, extension guide). **Checkpoint with user.**

### Stage 4 — Implementation increments (implementation phase 3)
1. Vertical slice + full trajectory capture: C03, C01.
2. As-of retrieval, reconciliation, sandbox, verifier, re-plan: C05, C07b, C04, C19.
3. Graph memory, cross-channel, specialists: C02/C02b, C08, C15, C16.
4. Panel, outreach, colleague statements, conservative default, memory curator: C06, C14, C18, C17.
5. Fan-out and populations, language/fairness, injection, servicing track, Q01: C11/C11b, C12, C10, C20, C09, C13, C07, Q01.

### Stage 5 — Full evaluation
All hero cases with pass^k and trajectory completeness; background precision/recall/FP rate vs legacy reviewers and scanner; calibration; fairness pairs; `docs/design/06-eval-results.md` with an annotated trajectory.

### Stage 6 — Observability console (later initiative)
Mirror CatcherAI's Dispute Observatory (`docs/prompts/03-…`, `docs/design/07-…`), with conduct-specific views: transcript viewer with verified evidence spans aligned to desktop events, said-vs-did timeline, panel debate, three-outcome provenance, Q01 selection view.

## Open questions (not blocking; defaults in parentheses)

1. Generate colleague-facing coaching notes, or only the assessment record? (assessment record + customer letter only)
2. Add collections servicing (Reg F) later? (no, out of POC scope)
3. Parameterized scenario families for per-category statistics? (not in Stage 1; background gold labels provide statistics)
4. Q01 capacity and random-slice share as console parameters? (yes, in Stage 6)
5. Keep `gpt-5.6-luna` as the runtime default, or switch providers? (keep, to reuse CatcherAI adapters; configuration-only change later)

## Known risks to watch in Stage 1

- **Transcript realism** is the biggest quality lever and the easiest to get wrong: background calls must read like real servicing calls, with misconduct at realistic subtlety — not caricatures.
- **Reviewer-noise calibration** must hit the reference baseline without making labels random on bright-line categories (noise should concentrate on judgment categories).
- **Discoverability vs leakage**: planted patterns must be findable by the intended queries without IDs, naming or `is_hero` giving them away.
- **Catalog drift**: any fact changed during implementation must be changed in catalog, data dictionary, ground truth and README together.
- Unverified research items (research §10) must stay out of load-bearing ground truth or be marked.

## Mandatory handoff maintenance after every stage

Update: header (date, phase, next stage), "What exists now", any new or changed decisions, the stage's status and acceptance evidence (commands run and results), known risks, and a dated entry in Stage history. Record deviations from the catalog or prompts explicitly, with the reason. **Then commit and push** (`git add -A && git commit && git push origin main`) — a stage is not complete until it is pushed.

## Stage history

### 2026-09-15 — Stage 0 design foundation complete
- Read the reference program brief and CatcherAI's structure (README, research, case catalog, data dictionary, kickoff prompt, handoff).
- Ran two parallel Sonnet research subagents (regulatory/enforcement; AI methods), reviewed their briefs and kept them under `docs/research/briefs/`.
- Designed the use case: Copperlake Bank, three channels, bilingual queue, 11-category misconduct taxonomy, three-outcome model, asymmetric conservative defaults, computed confidence, desktop events as screen substitute.
- Wrote the case catalog (23 heroes + Q01) with coverage matrices (every capability primary in ≥ 3 cases), failure-mode table, effective dates and SLA dates. Verified business-day SLA dates, weekdays and case arithmetic (fees, wpm, time-zone and clock-offset alignment) with a script.
- Research-driven changes to the first draft: added a diarization swap with channel metadata (C12); added the vacated $8 late-fee rule as stale memory (C07); SCRA note grounded in DOJ/OCC sources (C09); gating confidence changed from self-reported to computed; evidence spans and citations deterministically verified.
- Consistency fixes: aligned the panel-trigger rule with cases C05, C16 and C20 (now decided without a panel).
- Wrote the data dictionary, README, both kickoff prompts and this handoff.
- User set the standing rule: after every stage, update `handoff.md`, commit and push. Applied to the handoff and both kickoff prompts; Stage 0 committed and pushed to `origin/main`.
