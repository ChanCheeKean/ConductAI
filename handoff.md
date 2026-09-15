# ConductAI handoff

Last updated: 2026-09-15
Repository: `/Users/kean/Dev/ConductAI`
Branch: `main` (remote `origin` → `github.com/ChanCheeKean/ConductAI`)
Current phase: **Stage 4B — C01 transcript-integrity wait/resume: COMPLETE; awaiting user checkpoint**
Next stage: **Stage 4C — temporal evidence, reconciliation, sandbox, verifier/re-plan**

## Current objective

Build **ConductAI**, a proof-of-concept, fully automated agent system that reviews credit-card customer-service interactions (phone, chat, secure message) at the fictional **Copperlake Bank, N.A.** for sales and servicing misconduct. Stage 4 was split into smaller checkpointed substages because the implementation phase is large. Stages 4A–4B now prove both ends of the first vertical slice: C03's deterministic L1 early path and C01's bounded Deep Agents L2 investigation with private artifact scheduling, durable LangGraph suspension, process-independent resume, virtual time, transcript recovery and provenance-complete clearance. The next action is the user checkpoint before Stage 4C adds the temporal-evidence cases C05, C07b, C04 and C19.

The use case was inspired by an industry GenAI call-monitoring pilot (`docs/reference/reference-program-brief.md`); the problem set, data, cases and implementation are our own.

## Start here next session

Read, in order:

1. `handoff.md` (this file).
2. `docs/design/05-agent-architecture.md` — implementation blueprint and acceptance gates.
3. `docs/design/04-agent-architecture-research.md` — Stage 2 recommendation and evidence basis.
4. `docs/prompts/02-implementation-kickoff.md` — Stage 4 incremental implementation requirements in §7.
5. `README.md` — the foundation document (use case, ecosystems, memory, governance rules §8, generation §9, component → scenario §10, target layout §14).
6. `docs/design/02-case-catalog.md` — the contract for every hero case.
7. `docs/design/03-data-dictionary.md` — implemented file/field and ground-truth schemas.
8. `config/models.yaml`, `config/routes.yaml`, `config/scenarios/{c01,c03}.yaml` — implemented registries.
9. `src/conductai/adapters/runtime/langgraph_runtime.py`, `src/conductai/runtime/{c01,c03}_workflow.py`, and `src/conductai/harness/artifacts.py` — current vertical slices.
10. `data/generator/CONTRACT.md` and `data/corpus/CONTRACT.md` — implementation contracts.

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
| `docs/design/04-agent-architecture-research.md` | Four candidate architectures, current API verification, recommended hybrid/12-role roster, case fit, memory, safety and transparency design | complete |
| `docs/design/05-agent-architecture.md` | 963-line implementation blueprint: system/dependency boundaries, typed state, Mermaid graph, route/role/skill registries, tools, three memory planes, harness, 79-event v1 trajectory catalog, governance, termination, evaluation and extension guide | complete |
| `docs/prompts/01-data-foundation-kickoff.md` | Stage 1 session prompt | complete |
| `docs/prompts/02-implementation-kickoff.md` | Stages 2–5 session prompt | complete |
| `pyproject.toml`, `tests/test_derived.py` | Python 3.11+ stdlib project scaffold and derived-helper tests | complete |
| `data/corpus/` | Reproducible author, 53 versioned documents, 11 review skills, index and clause contract | complete |
| `data/generator/` | World, people, all hero builders, background/ASR, oversight, precedents, memory, sweep, graph, validation and loader | complete |
| `data/generated/` | 6,527 interactions/transcripts, structured/event/document ecosystems, 23 case truths + Q01, graph and manifest | complete; SQLite reproducible and git-ignored |
| `data/generated/conduct.sqlite` | Agent-visible tables plus FTS5 indexes (no evaluator/simulation data) | built locally by loader |
| `config/`, `skills/{credit-line-increase,add-on-consent}/` | Validated model/route/scenario registries and two Deep Agents-format skills | Stage 4B complete |
| `src/conductai/` | Domain models, config, guarded data, typed tools, router, runtime protocols, conditional LangGraph adapter, bounded Deep Agents lead, private artifact harness, C01/C03 workflows, event ledger/blobs/schema/replay and CLI | Stage 4B complete |
| `docs/schemas/` | JSON Schema exports for the 79-type v1 event envelope and assessment record | Stage 4A complete |
| `tests/{architecture,contract,unit,integration}/` | Import boundaries, gateway/config/access/ledger contracts plus C03 and C01 trajectory/replay/checkpoint acceptance | Stage 4B complete |

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
| Architecture control split | LangGraph/code owns obligations and deterministic gates; Deep Agents roles own bounded inquiry; domain records cross adapter boundaries; the application ledger is canonical | Stage 3 design |
| Role policy | 12 registered roles, selectively invoked by route/depth; L1 normally 0–1 role, L4 permits bounded fan-out and independent panel roles | Stage 3 design |
| Confidence formula | Provisional verifier-based weighted formula (25/20/25/20/10); non-applicable components renormalize; Stage 5 must calibrate it without changing CRM-003's 0.75 policy threshold silently | Stage 3 design |
| Runtime isolation | Agent/harness/evaluator views are separate; raw SQL/Cypher/filesystem and restricted datasets are inaccessible; local sandbox is POC containment, not a production security boundary | Stage 3 design |
| Implementation staging | Split former Stage 4 increment 1 into **4A C03 foundation** and **4B C01 wait/resume**, then preserve the remaining increments as 4C–4F | user requested smaller stages; keeps each checkpoint independently testable |
| C03 model use | No LLM call: the complete rule match and decisive records make C03 deterministic; the role stays registered for nontrivial paths | architecture permits zero or one L1 role; avoids decorative model use |
| Dependency baseline | Python 3.12; Deep Agents 0.7.14, LangGraph 1.2.11, OpenAI 2.54.0, Pydantic 2.13.5, locked in `uv.lock` | Stage 4A resolution |
| C01 model mode | The C01 lead runs through a real Deep Agents graph with a deterministic offline model for repeatable credential-free acceptance; policy gates, tools, waits and the final decision remain code-owned | Stage 4B; live provider smoke remains separate from deterministic CI |
| Wait durability | Artifact request/outbox state and LangGraph checkpoints share the run SQLite file; the harness releases content only after request and virtual availability, and resume works in a newly constructed runtime | Stage 4B acceptance requirement |

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

### Stage 1 — Data foundation: COMPLETE
Prompt: `docs/prompts/01-data-foundation-kickoff.md`.
Deliverables: `pyproject.toml` (uv), `data/corpus/` via `author_corpus.py` (regulation abridgements, SOPs, glossary v6/v7/v8, scripts, product disclosures, incentive plan, skills), `data/generator/` (world, 23 hero builders, background with transcripts + ASR/diarization noise, planted structures, derived arithmetic, capabilities, memory seed, precedents, on-request artifacts, personas, graph, manifest), `validate.py` (schemas, joins, arithmetic, capability coverage ≥ 3 primary cases each, discoverability, reviewer-baseline calibration, fairness hygiene), `load_sqlite.py` → `data/generated/conduct.sqlite`.
Acceptance met: `python3 data/generator/gen.py && python3 data/generator/validate.py` passes 377,519 checks; `load_sqlite.py` builds an integrity-clean SQLite database with 55 tables/virtual tables and three FTS5 indexes. Two clean regenerations are byte-identical (digest recorded in Stage history). Catalog facts were preserved; the dictionary and README carry actual counts.

### Stage 2 — Architecture research (implementation phase 1): COMPLETE
Prompt: `docs/prompts/02-implementation-kickoff.md` §4. Deliverable `docs/design/04-agent-architecture-research.md`: four candidates compared against ConductAI's cases; current OpenAI, Deep Agents, LangGraph, memory, graph/vector, observability, contact-center and safety interfaces re-verified; recommended hybrid and 12-role selective roster documented. Checkpoint passed when the user asked to continue on 2026-09-15.

### Stage 3 — Architecture design (implementation phase 2): COMPLETE
Deliverable `docs/design/05-agent-architecture.md`: exact system/runtime boundaries, typed state and review file, Mermaid graph, route and 12-role registries, tool schemas, skills, three-plane memory flows, harness/isolation, gateway/runtime protocols, complete v1 event catalog, governance as code, termination, evaluation, contract tests and extension guide. Checkpoint passed when the user asked to continue on 2026-09-15.

### Stage 4 — Implementation substages (implementation phase 3)
1. **Stage 4A COMPLETE:** runtime/config/data/tool/ledger/replay foundation + C03 L1.
2. **Stage 4B COMPLETE:** C01 transcript integrity, Deep Agents lead, artifact request, durable suspend/resume and virtual clock.
3. **Stage 4C NEXT:** as-of retrieval, reconciliation, sandbox, verifier and re-plan: C05, C07b, C04, C19.
4. **Stage 4D:** graph memory, cross-channel and specialists: C02/C02b, C08, C15, C16.
5. **Stage 4E:** panel, outreach, colleague statements, conservative default and memory curator: C06, C14, C18, C17.
6. **Stage 4F:** fan-out/populations, language/fairness, injection, servicing track and Q01: C11/C11b, C12, C10, C20, C09, C13, C07, Q01.

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

## Known risks carried into implementation

- **Transcript realism** remains the biggest quality lever: Stage 1 uses deterministic template grammar and compact hero dialogue; production-like expansion would need more linguistic variety and audio-derived evidence.
- Reviewer baselines are deterministically calibrated to target aggregate precision/recall; future evaluation should avoid treating those synthetic historical labels as independent human judgments.
- **Discoverability vs leakage**: planted patterns must be findable by the intended queries without IDs, naming or `is_hero` giving them away.
- **Catalog drift**: any fact changed during implementation must be changed in catalog, data dictionary, ground truth and README together.
- Unverified research items (research §10) must stay out of load-bearing ground truth or be marked.
- The Stage 3 computed-confidence weights and route budgets are explicit POC starting values, not calibrated production thresholds; Stage 5 must report calibration and threshold sensitivity.
- The restricted local subprocess is a POC containment control, not a hostile-code boundary; a production deployment needs a container or microVM with the same contract.
- Stages 4A–4B deliberately implement only C03 and C01 graph paths. The fallback route fails closed; it must not be treated as a general reviewer until later substages land.
- The OpenAI Responses adapter is contract-tested offline, while C01's Deep Agents acceptance run deliberately uses a deterministic offline model. The real API smoke test and live Deep Agents/provider bridge have not been exercised yet.

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

### 2026-09-15 — Stage 1 data foundation complete
- Authored the corpus reproducibly from `author_corpus.py`: 53 effective-dated regulation/policy/glossary/script/product/incentive documents and 11 procedural skills. Clause references are validated against headings.
- Implemented the stdlib-only deterministic generator: static world and people, all 23 hero builders, seven planted structures, 6,500-interaction background, ASR and diarization noise, reviewer/scanner baselines, precedents, memory, Q01 sweep and graph projection.
- Generated 6,527 total interactions/transcripts, 41,873 event rows, 6,369 document rows, 40 precedents, 58 memory notes, four on-request artifacts, four personas, and a 10,023-node/27,259-edge graph. Background gold misconduct is exactly 234/6,500 (3.6%).
- Legacy reviewer baselines are confined to the pre-2026-10-01 historical slice and hit the requested bands: R-A 78.64/76.42, R-B 74.26/70.75, R-C 75.23/77.36 precision/recall. Q01 risk-ranked recall is 71.43% with the required hero set inside its 36 picks.
- `validate.py` passed 377,519 independent checks over corpus metadata/clauses, schemas, joins, timing, arithmetic, planted discoverability, capability coverage, calibration, fairness hygiene and evaluator leakage.
- Two clean regenerations were byte-identical across every generated non-SQLite file: aggregate SHA-256 `ab157236ad0ae2ffab339ea6ac3d0f59fd02ac4b9e8e015957fc60f02f656bcf`.
- `load_sqlite.py` built `data/generated/conduct.sqlite` (28,962,816 bytes), SQLite `integrity_check` returned `ok`, and FTS5 indexes cover transcript turns, corpus chunks and documents. The DB is reproducible and git-ignored.
- Deliberate scope choice: background event/document density is 41,873/6,369 rather than the design's early ~180k/~9k target; this retains the required modalities and discoverability while keeping the POC repository compact. Hero facts and planted population counts did not change.

### 2026-09-15 — Stage 2 architecture research complete
- Re-read the implementation prompt, foundation, case/data contracts, generated manifest, domain research, and CatcherAI's research/design/evaluation/handoff; evaluator-only and harness-gated data stayed unread.
- Re-verified current official interfaces for the exact `gpt-5.6-luna` model and Responses API, the stable Python Codex SDK, Deep Agents 0.7.x, LangGraph typed streaming/checkpoints/`Send`/resume semantics, AG-UI, LangSmith, OpenTelemetry, LadybugDB, sqlite-vec, Graphiti and LangMem.
- Compared four candidate architectures and selected a deterministic LangGraph compliance graph around one lead Deep Agent, with 11 additional registered roles invoked selectively, bounded `Send` fan-out for C11/C12/Q01, and deterministic reducers/gates. Deep Agents async subagents were rejected for the initial POC because their Agent Protocol server control plane conflicts with the local-only requirement.
- Specified what transfers unchanged from CatcherAI: provider/runtime seams, event envelope, transactional emitter/blob store/hash chain, replay adapters/CLI pattern, instrumentation choke points, resolved configuration, governance-as-code structure and trajectory completeness tests. Dispute logic and outcome semantics do not transfer.
- Documented the transparency design: application-owned SQLite ledger as source of truth, framework streams/checkpoints as inputs, AG-UI/OTel as outward projections, and conduct-specific transcript, said-vs-did, memory, panel, provenance and Q01 views.
- Acceptance check: `python3 data/generator/validate.py` remained green at **377,519 checks**; `git diff --check` passed.
- Corrected the stale README status left from Stage 0. No catalog fact, generated datum, or ground-truth contract changed.

### 2026-09-15 — Stage 3 architecture design complete
- Converted the recommended hybrid into a 963-line implementation blueprint with a deterministic outer graph, explicit back-edges and waits, bounded C11/C12/Q01 fan-out, typed checkpoint state and a source-cited review-file blackboard.
- Specified deterministic-first routes, the 12-role selective registry, all 11 authored skills, depth budgets, typed/instrumented read, external-event, computation, action and memory tools, and the model-gateway/agent-runtime replacement seams.
- Defined persistent, semantic/vector and graph memory interfaces; selective read, write, consolidation and forgetting; bitemporal lifecycle semantics; colleague-only pattern scope; and explicit NetworkX fallback behavior.
- Defined harness isolation with physically/logically separate agent, simulation and evaluator views; virtual-clock artifact/persona scheduling; latest-safe-time behavior; and denied access to ground truth, `is_hero`, simulation and unreleased artifacts.
- Enumerated the complete 79-event v1 trajectory union with an example payload, mandatory emitter and frontend consumer for every event; specified hash-chained SQLite persistence, content-addressed blobs, redaction, replay, AG-UI/SSE projection and transparency reconciliation tests.
- Coded the exact panel predicate, provisional verifier-based confidence formula, independent advocates, conservative defaults, allowed/forbidden action controls, closed termination enum, corrupt-success evaluation rules, capability mapping, extension paths and implementation gates.
- Acceptance checks: `python3 data/generator/validate.py` remained green at **377,519 checks**; all 3 derived-helper unit tests passed; an architecture-contract check found all required sections, exactly 79 cataloged event types and balanced code fences; `git diff --check` passed. No case fact, generated datum, corpus contract or ground-truth contract changed.

### 2026-09-15 — Stage 4A runtime foundation + C03 L1 complete
- Split the large implementation phase into 4A–4F at the user's request. Stage 4A is the smallest complete vertical slice; C01 wait/resume moved intact to 4B.
- Added immutable Pydantic/YAML model and route configuration with a secret-free content-hashed run snapshot. Preserved exact OpenAI `gpt-5.6-luna` Responses configuration after checking official OpenAI documentation; credentials remain environment-only.
- Locked the Python 3.12 environment: Deep Agents 0.7.14, LangGraph 1.2.11, `langgraph-checkpoint-sqlite` 3.1.1, OpenAI 2.54.0, Pydantic 2.13.5 and PyYAML 6.0.3.
- Implemented provider-neutral model/runtime protocols, deterministic fake and OpenAI Responses gateways, and architecture tests that prohibit provider/framework imports outside adapters.
- Implemented guarded read-only operational queries with virtual availability filters and explicit denials for evaluator/harness resources; typed Pydantic tool schemas and a single executor produce paired call/result, SQL and budget events.
- Implemented the C03 `cli_soft_pull_clean` route through a real LangGraph graph with 11 mandatory nodes and durable SQLite checkpoints. It loads only the CLI skill, verifies the exact source turn and `CLB-POL-CLI@v6` as of the interaction date, computes the inquiry rule, confirms `BIR-9000401` was SOFT, records no error and deliberately skips memory.
- Implemented the complete 79-name v1 event union, transactional per-run sequencing, SHA-256 hash chaining, content-addressed/redacted blobs, assessment persistence, complete leaf-level provenance, JSON Schema exports, replay to any sequence and CLI run/replay commands.
- C03 acceptance trajectory: **84 events**, **5 tool calls**, **0 model calls**, **11 node enter/exit pairs**, **11 ledger checkpoint events**, **at least 11 LangGraph persisted checkpoints**, final event `termination{reason=assessment_complete}`; hash chain and final assessment replay both reconcile.
- Acceptance checks: `uv run pytest -q` passed **19 tests**; `python3 data/generator/validate.py` remained green at **377,519 checks**; JSON schemas regenerated; `python3 -m compileall -q src tests` and `git diff --check` passed. No case fact, generated datum, corpus contract or ground-truth contract changed. Real OpenAI smoke test intentionally not run because C03 makes no model call.

### 2026-09-15 — Stage 4B C01 transcript-integrity wait/resume complete
- Added the data-driven `addon_consent_integrity` L2 route, the Deep Agents-format `add-on-consent` skill and the C01 scenario registry. C03 remains on its unchanged deterministic L1 route.
- Implemented a bounded lead behind the runtime-neutral `LeadReviewer` contract. Its Deep Agents graph makes one deterministically recorded offline model call, opens unauthorized-enrollment vs ASR-error hypotheses, and selects re-transcription because the low-confidence polarity words can flip every outcome. Mandatory integrity, evidence, verifier, decision and memory gates remain code-owned.
- Expanded guarded operational reads for word-level transcript quality, add-on enrollments and desktop events. C01 reads six typed tools total; every call/result remains paired with registered SQL, source refs and budget events.
- Added the harness-private artifact scheduler and durable request/outbox table. The agent cannot read `on_request/**`; only the harness reads the registered artifact after an idempotent request and its virtual release time. A failed resume can safely retry because release is acknowledged only after the graph advances successfully.
- Refactored the outer LangGraph into explicit conditional paths. C01 checkpoints the artifact request, suspends at a pure LangGraph `interrupt`, advances virtual time from **15:00Z to 19:00Z**, restores from SQLite in a newly constructed runtime, ingests `RTX-9000101`, and takes the logged `ingest_artifact → integrity` back-edge. The CLI automatically drives allowed external waits to completion without a human gate.
- Recovered evidence says **“Oh — I do need that. Go ahead.”** The verifier confirms the exact span, `CLB-SOP-SAL-001@v4` §§3.1/3.2/4.1, price-before-consent and enrollment-after-consent/during-call; all three outcomes are no error/none, and `memory_write_skipped` prevents a false colleague lesson.
- C01 acceptance trajectory: **58 events at suspension; 128 after resume; 6 tool calls; 1 Deep Agents/model call; 2 transcript assessments; 1 artifact request/arrival; 1 clock advance; 1 checkpoint restore; 17 graph edges including the required back-edge; 16 application checkpoint events and 23 persisted LangGraph checkpoints**. Final event is `termination{reason=assessment_complete}`; event virtual times are monotonic, the hash chain verifies, and assessment replay/provenance reconcile.
- Acceptance checks: `uv run pytest -q` passed **24 tests** including restart-safe resume, future-artifact invisibility, request/release idempotency and conflict rejection; `python3 data/generator/validate.py` remained green at **377,519 checks**; `python3 -m compileall -q src tests` and `git diff --check` passed. No catalog fact, generated datum, corpus contract or ground-truth contract changed. Real OpenAI smoke remains intentionally unrun; deterministic C01 CI uses the offline Deep Agents model.
