## Who you are and what we're building

You are the lead engineer for **ConductAI**, a proof-of-concept **agentic conduct-review system** for a credit-card issuer (Copperlake Bank, N.A., fictional). It reviews customer-service interactions — phone transcripts, chat logs and secure messages — together with the systems of record a human conduct reviewer would check (desktop activity, offers, enrollments, product changes, ledgers, flags, preferences, callbacks, complaints, incidents) and the versioned glossary, scripts, policies, disclosures and regulation, to detect sales and servicing misconduct and decide what restores the customer, whether a colleague is at fault, and what control failed. The foundation is already done: domain research, 23 hero reviews plus a portfolio sweep with machine-checkable ground truth, a synthetic data ecosystem (~6,500 interactions at 3.6% gold misconduct prevalence with noisy legacy reviewer labels), a versioned corpus, skills, seeded agent memory, on-request artifacts and a memory/governance design.

Your job in this session is to **research how best to build it, propose an architecture, and then implement it** initially on **LangChain Deep Agents (`deepagents`) + LangGraph**, using **OpenAI `gpt-5.6-luna` as the default backbone model through the Responses API**. The conduct-review workflow must not be coupled to OpenAI, a LangChain model class, Deep Agents, or any provider SDK: model changes must be configuration-only, and replacing the agent runtime later (for example with the Codex SDK) must require a new adapter rather than changes to review logic, tools, memory, governance, evaluation or trajectory consumers. It must robustly solve the use case, be easy to extend, show every step transparently, and look genuinely state-of-the-art.

Work in three phases, with a checkpoint with me after phases 1 and 2 (details at the end).

> **Development-process subagents (not ConductAI runtime behavior):** if you delegate research, design, implementation, debugging or review work to subagents while carrying out this prompt, use **Sonnet** by default for normal, well-scoped work, and gather the results back into this session. Use **Opus** only for genuinely complicated work that needs deeper reasoning or broad cross-cutting synthesis — for example consequential architecture decisions, difficult multi-module debugging, security/compliance review, or resolving conflicting evidence. This instruction governs the engineering session's own subagent model selection only; it must **not** be implemented as ConductAI model-routing logic, added to the framework's runtime configuration, or included in product trajectories/evaluations.

> **Non-negotiable: the system is fully automated. No human in the loop.** No human testers, approval gates, review queues, interrupts that wait for a person, or simulated human reviewers. Every review must reach final, executed outcomes automatically. High-impact or uncertain findings are handled by automated governance (`data/corpus/policies/CLB-SOP-CRM-003__v4.md`): a customer-advocate and colleague-advocate review panel, an independent adjudicator, verifier checks, a **computed** confidence with a 0.75 threshold for adverse colleague findings, a conservative default (customer-protective remediation, no adverse colleague finding, coaching and enhanced monitoring allowed), and bounded automated actions (never employment, disciplinary or compensation actions). Runs may suspend **only** for external events (re-transcriptions, audio recovery, colleague statements, simulated customer replies, scheduled follow-ups) and must decide by the latest safe decision time derived from the monitoring SLA. (The phase checkpoints below are for our development process, not part of the system.)

> **Non-negotiable: full transparency. No silent steps.** A frontend will replay every run. Every step must be logged as a structured event: every graph node and edge, routing decision, plan change, model call, **tool call (which tool, why, with what arguments, what came back)**, subagent delegation, skill load, **memory access (which store, which query and filters, which records came back, which were used or discarded, what was written, superseded, rejected, purged or deliberately *not* written)**, computation, artifact arrival, clock change, untrusted-content detection, panel position, verifier check, finding, outcome and termination. Every assessment field must link back to the events and source IDs that justify it. If it isn't in the event log, it didn't happen. See §5 "Transparency".

---

## 1. Read these first (in this order)

| File | Why |
|---|---|
| `README.md` | The foundation: use case, domain background, data/evidence/policy ecosystems, memory design (§6), **automated governance rules (§8)**, generation approach, **architecture component → forcing scenario (§10)**, evaluation design, production gaps, assumptions |
| `docs/research/01-domain-research.md` (+ `briefs/`) | UDAAP and the card rules behind each case, enforcement history, industry QA and vendor practice, and the AI-methods findings that constrain the design (computed confidence, citation verification, ASR/diarization risk, injection, fairness, low-prevalence evaluation) |
| `docs/design/02-case-catalog.md` | The 23 hero reviews (C01–C20, C02b, C07b, C11b) + Q01: what each proves, expected review path, pivots, traps, scanner and single-prompt failure modes, SLA dates, the coverage matrix |
| `docs/design/03-data-dictionary.md` | Every file and field, ID joins, clocks (UTC platform, local CRM, skewed workstations), transcript schema with word/speaker confidence and channel metadata, on-request artifacts, memory-note schema (bi-temporal), graph schema, **assessment-record output schema (§9)**, ground-truth schema (§10), deliberate data-quality issues |
| `data/corpus/**/*.md` | Versioned regulation, SOPs, glossary, scripts, product disclosures, incentive plan (front matter: `doc_id`, `effective_from/to`, `status`, `supersedes`) |
| `data/corpus/skills/*.md` | Review playbooks (convert to the Deep Agents `SKILL.md` format as needed) |
| `data/generated/manifest.json` | What exists and how much |
| `data/generator/validate.py`, `data/generator/derived.py` | Discoverability queries; business-day, time-zone, clock-offset, wpm and fee arithmetic (reuse or port into sandbox helpers) |
| `/Users/kean/Dev/CatcherAI/docs/design/04-agent-architecture-research.md`, `05-agent-architecture.md`, `06-eval-results.md`, `handoff.md` | The sibling project that solved the same engineering problems for card disputes. Reuse what transfers (gateway/runtime boundaries, event envelope, emitter, replay, evaluator, governance-as-code); do not copy dispute logic |

Commands:
```bash
python3 data/generator/gen.py && python3 data/generator/validate.py   # regenerate + validate
python3 data/generator/load_sqlite.py                                 # build data/generated/conduct.sqlite
```

**Hard rule:** the agent must **never** read `data/generated/ground_truth/**`, `data/generated/simulation/**` or unreleased `data/generated/on_request/**`, and never see `is_hero`. Enforce this with filesystem permissions or backend routing, not just instructions.

---

## 2. The problem in brief (details in the docs)

### How the industry flow works
Customer contacts the issuer (phone, chat, secure message) → recording, ASR (routed by language), redaction → the colleague services the request and may present offers, enroll add-ons, change products, waive fees or handle a complaint, using a desktop that records every action → post-interaction outcomes (cancellations, complaints, statements, bureau inquiries) → **conduct risk monitoring** selects interactions (keyword/structured scanners, complaints, lookbacks, samples) → reviewers combine the recording, screen activity, misconduct glossary, policies, sales instructions and product disclosures → outcome: no error or a misconduct category → customer remediation, colleague coaching, control fixes. **Customer harm, colleague fault and control cause are separate decisions.**

### How the industry solves it today
- **Human QA:** small samples per colleague scored on scorecards mixing must-pass compliance items and soft skills; red-flag phrase libraries; two-level tester review in the reference GenAI pilot (AI precision 65% / recall 78% vs reviewers 74–79% / 71–77%).
- **Vendors:** NICE Enlighten, Verint, CallMiner, Observe.AI, Level AI (configurable rubrics over tagging backbones), Cresta/Balto (real-time guidance), AWS Contact Lens (rules + GenAI categories). Genesys requires human approval of AI scores — fully automated verdicts are not current vendor practice.
- **Where they break:** keyword lists miss paraphrase and over-fire on accurate statements; transcripts are trusted despite ASR and diarization errors; screen activity and systems of record aren't joined to speech; rules are applied without version dates; colleagues are blamed for scripts, systems and supervisors' material; patterns are applied to teammates; stated model confidence is used as if calibrated; monitored content can steer the monitor.

### What our system must do
For each review: understand the trigger → route it (track, channel, language, depth) → plan → assess transcript integrity and get better evidence when a decisive span is weak → retrieve glossary/script/policy/disclosure **as of the interaction date** → join speech to desktop events and records with correct clocks → traverse related interactions, colleagues, teams, materials and incidents → call tools and subagents → request and wait for artifacts and replies → detect contradictions → compute in a sandbox → find and distinguish precedents → revise the plan when root cause shifts → track claims, hypotheses and open questions → reach evidence-verified findings with computed confidence → decide customer, colleague and control outcomes separately → challenge high-impact findings through the automated panel (`CLB-SOP-CRM-003@v4`) → execute bounded actions → govern its own memory → leave a full auditable trajectory. Portfolio level: select the week's reviews under capacity with a protected random slice (Q01). **All of it without a human.**

The **assessment record** (data dictionary §9) is the output contract the evaluator checks against `ground_truth/cases/<review_id>.json`.

---

## 3. Mandatory components — all of these MUST be implemented and demonstrably used

The solution is **not acceptable** unless every component below is implemented, genuinely load-bearing, and **provably used** in the trajectories of the cases that need it:

1. **Agents**
2. **Router**
3. **Loop engineering (with real termination conditions)**
4. **Agent graph engineering**
5. **Subagents**
6. **Tool / function calling**
7. **Harness**
8. **Skills**
9. **Memory: persistent, graph, and semantic/vector** (all three)
10. **Sandbox or REPL for computing over data**
11. **Agent read paths and agent write paths** (selective read, selective write, consolidation and forgetting)

The dataset already contains cases that **cannot be solved without each one**:
- **Per case:** `required_capabilities` in `data/generated/ground_truth/cases/<review_id>.json` (capability, `necessity`, why, and the trajectory events that prove use).
- **Summary:** `data/generated/ground_truth/capability_coverage.json` and §2 of `docs/design/02-case-catalog.md`.

Every component is *primary* in at least three cases:

| Component | Primary cases |
|---|---|
| Agents | C06, C11, C12, C14 |
| Router | C02, C03, C10, C13, C15, Q01 |
| Loop engineering (real termination conditions) | C01, C03, C06, C17, C18 |
| Agent graph engineering | C04, C06, C11, C12, C14 |
| Subagents | C06, C11, C12, C14, Q01 |
| Tool / function calling | C01, C05, C16, C20 |
| Harness | C01, C06, C10, C15, C17, C18, Q01 |
| Skills | C05, C08, C09, C13, C17 |
| Memory — persistent (SQLite system of record) | C02, C05, C07b, C15, C16, Q01 |
| Memory — graph | C02, C02b, C08, C11, C11b, C12 |
| Memory — semantic / vector | C04, C09, C12, C17, C19 |
| Sandbox / REPL | C04, C05, C07b, C10, C11, C16, C18, C20, Q01 |
| Agent read paths (selective read) | C04, C10, C11b, C14, C19 |
| Agent write paths (selective write, consolidation, forgetting) | C03, C04, C11, C11b, C12, C14, C19 |

**Acceptance criteria:**
- The evaluator checks capability usage from the trajectory event log, not just final answers. For every case, each `primary` capability must appear through its trajectory signals (e.g. `route_decision`, `termination{reason}`, `wait_suspended/resumed`, `edge_taken` back-edges, `subagent_started/finished`, `skill_loaded`, `graph_query`/`graph_write`, `retrieval{filters}`, `computation`, `memory_read` + `memory_verified/rejected`, `memory_write/supersede/retract/consolidate/purge`, `memory_write_skipped`, `write_rejected`, `artifact_requested/arrived`, `untrusted_content_flagged`).
- A case that reaches the right answer without using its primary capabilities counts as a **capability failure**.
- Report a capability × case matrix of pass/fail in the eval results.
- Honor `memory_ops.must_not_write` and `must_not` in the ground truth: selective write means also **not** writing (and logging the decision not to write); fairness means never citing prohibited attributes.
- **Trajectory completeness is scored too:** a run fails if any model call, tool call, memory/graph/vector access, sandbox execution or state-changing node has no matching event, or if any assessment-record field lacks provenance links.
- **Detection quality is scored on the background:** interaction-level precision, recall and FP rate vs gold, reported side by side with legacy reviewers R-A/R-B/R-C and the scanner.

### Capability details (minimum bar)

Use README §10 and the catalog's coverage matrix to tie every capability to the cases that force it. Nothing decorative.

| Capability | Minimum bar |
|---|---|
| **Agents** | goal-directed reviewers that choose what evidence to pursue next and when a root-cause hypothesis has shifted |
| **Router** | review-level: track (sales / servicing / mixed), channel, language, depth (L1–L4), trigger type, obvious non-issues; portfolio-level weekly selection with a protected seeded random slice and **permitted features only** (Q01). Routes must be **data/config-driven** so new routes can be added without touching code |
| **Loop engineering with real termination conditions** | explicit, logged stop reasons: assessment complete and verifier passed; budget exhausted (tool calls / tokens / wall-clock); **suspended waiting for an external event** (virtual clock, `available_at`) with checkpoint and resume, or decide at the latest safe decision time; conservative default applied after the panel; no-progress detection; max re-plans reached. L1 reviews must stop early |
| **Agent graph engineering** | a LangGraph graph with explicit nodes and edges (e.g. intake → route → integrity check → gather → reconcile → verify → panel (when required) → decide outcomes → act/write → memory maintenance), including **back-edges** (verify → re-plan; reconcile → re-route), conditional edges, parallel fan-out, and suspend/resume on external events |
| **Subagents** | specialist subagents via Deep Agents (`task` tool, custom `SubAgent`s; evaluate **dynamic subagents** for fan-out per linked interaction in C11, per phrase hit in C12, per candidate in Q01). Likely specialists: transcript-integrity analyst (ASR, diarization, gaps, re-transcription), desktop/records reconciler (said vs did, clocks), policy analyst (as-of retrieval across glossary/script/policy/disclosure), colleague-history analyst (graph + statistics), population analyst (control-gap scope), customer-remediation planner, customer advocate, colleague advocate, adjudicator, verifier, memory curator. Research and justify the final set, don't just adopt this list |
| **Tool / function calling** | typed tools (Pydantic schemas) over SQL, transcripts (turns, words, speaker/channel metadata), desktop events, graph, vector/FTS search (with `as_of`, speaker, channel filters), artifact requests (re-transcription, audio recovery, colleague statement), customer outreach, remediation and control actions, memory operations, sandbox execution |
| **Harness** | virtual clock and `available_at` gating; on-request artifact release with delays; simulated customer (persona-driven, τ-bench style, from `simulation/customer_personas.json`); colleague statements; scheduled follow-ups; scenario loader; budgets; trajectory capture; eval runner |
| **Skills** | Deep Agents skills (`SKILL.md`, progressive disclosure) built from `data/corpus/skills/`; route-selected; new skills are drop-in directories |
| **Memory: persistent** | SQLite system of record (interactions, records, events, transcripts, review state, memory-note lifecycle table); LangGraph checkpointer for thread state |
| **Memory: graph** | LadybugDB (embedded Cypher) loaded from `graph/*.jsonl`, NetworkX fallback behind the same small interface; agent writes hypothesis nodes/edges (`ConductPattern`, `UnapprovedMaterial --USED_IN-->`) with evidence edges and `status=active`, strictly scoped (a colleague pattern never attaches to teammates) |
| **Memory: semantic/vector** | sqlite-vec (same SQLite file) over corpus chunks, transcript segments, precedents, complaints, CRM notes, internal comms and memory notes, with **metadata filtering** by effective date / validity window / status and by **speaker and channel** for transcript segments, plus hybrid keyword search (FTS5) |
| **Working memory** | per-review "review file" (claims with turn IDs and record IDs, evidence matrix said/did/recorded, hypotheses, open questions, deadlines, plan) in the Deep Agents virtual filesystem, shared across subagents as a blackboard |
| **Sandbox / REPL** | Python execution for business-day SLAs with holidays, time zones (Arizona has no DST), workstation clock offsets, speech-to-event alignment, words per minute, fee/premium/refund arithmetic, cancellation-rate statistics, affected populations, Q01 scoring; read-only data access; code and output recorded in the trajectory. Evaluate Deep Agents sandbox backends vs a local restricted subprocess |
| **Agent read paths** | **selective read**: retrieval scoped by interaction, colleague, team, product, `as_of` date, validity window, confidence and status (never superseded/retracted/purged notes as current; never another colleague's pattern); memory treated as a lead to verify, never as evidence |
| **Agent write paths** | **selective write**: the agent decides *whether* something is worth remembering; a write gate validates schema (`source_refs`, validity, confidence, scope), blocks prohibited content (`CLB-SOP-CRM-004`) and dedupes; outcomes, letters and control records are writes too |
| **Consolidation & forgetting** | supersede, retract (with correction note), consolidate (≥ 3 observations → validity-bounded note), time-bound, dedupe, expire (TTL), purge (prohibited content, keep tombstone), recency/access decay; bi-temporal (valid time + record time). Seeded examples: MEM-0310, 0320, 0341–0343, 0350–0356, 0396, T-SAT-2 observations (README §6). Run as an in-review step and as an offline "memory curator" job |
| **Automated governance (no human in the loop)** | panel triggers, advocates and adjudicator, verifier checks, computed confidence, 0.75 threshold, conservative default, allowed and forbidden actions per `CLB-SOP-CRM-003@v4` (README §8) — every position, confidence component and flip fact recorded (C04, C06, C08, C09, C11, C12, C14, C18) |
| **Transparency / trajectory** | one instrumentation point captures every step (§5); replayable to any `seq`; field-level provenance; CLI replay viewer before the frontend; completeness tests that fail on silent steps |
| **Evaluation** | run all cases; deterministic checks, `must_not`, required facts and contradictions, required citations and verified evidence spans, memory ops, budget adherence, **pass^k** reliability, cost/latency, Q01 recall and random-slice reproduction, background precision/recall/FP rate vs legacy reviewers and scanner, per-category and colleague-level recall, calibration (ECE/Brier) of computed confidence, fairness matched pairs, injection robustness; optional rubric judge. Trajectory evaluation too |

---

## 4. Research first (phase 1): search broadly, then synthesize

Before designing, research how others build systems like this and bring back **several distinct approaches** we can combine. Use web search, GitHub search and the Context7 docs tool. Cite everything and separate proven practice from marketing.

**Research is not budget-constrained.** Go as wide and deep as the problem needs:
- The directions below are **starting points, not limits**. Follow citations, related repos, issues and discussions wherever they lead.
- Read actual source code, not just READMEs: clone relevant repos into a scratch directory and inspect how they implement agents, memory, event streams and evals.
- When docs are unclear or possibly stale, **run small throwaway spikes** to confirm behavior before relying on it.
- Run research threads in parallel (research subagents per direction, on Sonnet) if that is faster.
- Research can continue in phases 2 and 3 whenever a question comes up. Record new findings in the research doc.
- **Start from CatcherAI's `04-agent-architecture-research.md`** — re-verify framework APIs that may have moved and spend new effort on what is specific to conduct review.

Directions:

**A. The framework (verify current APIs; the library moves fast)**
- Deep Agents: `create_deep_agent` parameters, `SubAgent`/`CompiledSubAgent`, **dynamic subagents**, skills, backends (`StateBackend`, `StoreBackend`, `FilesystemBackend`, `CompositeBackend`, sandbox backends, permissions), memory (`AGENTS.md`), summarization/offloading, typed event streams, middleware hooks.
- LangGraph: `StateGraph`, conditional edges, `Send` fan-out, subgraphs, `interrupt`/`Command` resume (for external events only), SQLite checkpointers, `Store` with namespaces/semantic search, streaming modes, time travel/replay.
- LangChain examples: `open_deep_research`, `deep-agents-ui`, `agent-chat-ui`, supervisor/swarm patterns, `langmem`, `agentevals`, LangSmith tracing and evals.
- OpenAI: `gpt-5.6-luna`, the Responses API, structured outputs, tool calling, streaming, reasoning controls, usage/cached-token reporting, retries and prompt caching; the Codex SDK as a **future agent-runtime adapter**. Official docs: `https://developers.openai.com/api/docs/models/gpt-5.6-luna`, `https://developers.openai.com/codex/sdk`.

**B. Multi-agent design: how many agents, which roles**
- Anthropic "How we built our multi-agent research system" and "Building effective agents"; OpenAI "A practical guide to building agents"; Magentic-One; MetaGPT; blackboard architectures; supervisor vs swarm vs hierarchical; when a deterministic workflow should wrap an LLM agent (compliance gates).
- Agent count vs coordination cost; context isolation; fan-out over populations (tens of linked interactions).

**C. Domain implementations on GitHub and the web**
- Search: "call center QA LLM", "auto QA agent", "sales compliance monitoring LLM", "mis-selling detection", "conversation compliance agent langgraph", "UDAAP compliance AI", "complaint classification LLM bank", "conduct risk surveillance AI", "trade surveillance LLM" (communications surveillance is a close cousin), "speech analytics compliance".
- Cloud reference architectures: AWS Contact Lens / Amazon Connect generative AI, Google Conversational Insights, Azure AI Language conversation analytics, NICE/Verint/CallMiner/Observe.AI/Level AI technical material. Extract decision logic, not marketing.
- Papers: τ²-bench (dual control), procedure-aware "corrupt success" evaluation, RIRAG/ObliQA, LLM-as-judge reliability and calibration, counterfactual fairness in contact-center QA (arXiv 2602.14970), diarization confidence (arXiv 2406.17124), AgentDojo, low-prevalence evaluation. Study what the reference program's **two human testers** were catching and how our panel and verifier replace them.

**D. Memory architectures**
- Zep / **Graphiti** (bi-temporal validity; relevant to versioned glossaries and colleague patterns with change points), Letta/MemGPT, Mem0, A-MEM, Generative Agents (reflection), Cognee, LangMem; consolidation, decay, conflict resolution; GraphRAG / LightRAG for policy-plus-entity retrieval; scoping to avoid cross-entity contamination (colleague ↔ teammate).

**E. Reasoning and reliability techniques**
- Plan-and-execute with re-planning; Reflexion / self-refine; verifier-critic loops; adversarial debate; CodeAct and smolagents; structured outputs; **computed vs self-reported confidence**, conformal prediction for judge panels, abstention; deterministic span/citation verification; tool-grounded arithmetic and time alignment; two-pass extraction (per call phase) then reconciliation.

**F. Transparency and frontend-ready trajectories** (this shapes the event schema, so go deep)
- AG-UI protocol; LangGraph streaming (`updates`, `messages`, `custom`, `debug`, subgraphs); Deep Agents typed event streams; middleware hooks around model and tool calls; checkpoint history and time travel.
- LangSmith, Langfuse, Arize Phoenix / OpenInference, OpenLLMetry, W&B Weave, AgentOps, OpenTelemetry GenAI semantic conventions.
- UIs: deep-agents-ui, agent-chat-ui, LangGraph Studio, trace viewers. For conduct review specifically: transcript viewer with evidence-span highlighting aligned to desktop events, said-vs-did timeline, panel debate view.
- Audit expectations: SR 11-7 model risk management, EU AI Act record-keeping, CFPB supervision expectations for complaint handling and remediation, employee due process for conduct findings. What must an examiner, an internal auditor or a colleague's appeal be able to reconstruct from the log?
- How to keep the log complete without scattering logging code everywhere. **CatcherAI already built this** — evaluate reusing its envelope, emitter, blob store, hash chain and replay.

**G. Safety for this domain**
- Prompt injection via transcripts, chat, CRM notes and internal comms (monitored content is adversarial; colleagues know they are monitored); least-privilege tools; PII/PCI redaction before any model or index; fairness guardrails for customers **and** colleagues (ECOA/Reg B prohibited bases; language and accent; ASR quality must not proxy for either).

**H. Anything else that matters**
- Anything state-of-the-art that would make the system more robust, more explainable or more impressive to a conduct-risk, compliance and AI-engineering audience. Bring it back with evidence.

**Phase 1 deliverable:** `docs/design/04-agent-architecture-research.md` with 3–5 candidate architectures (e.g. deterministic LangGraph workflow wrapping one Deep Agent reviewer; supervisor Deep Agent with a fixed specialist team; hybrid with deterministic evidence checks, a verifier gate, an automated panel and an offline memory curator; dynamic fan-out for populations; event-sourced blackboard), each with pros/cons against **our** cases, recommended agent count and roles, what to borrow from each source (including what to reuse from CatcherAI unchanged), a recommended combination, and a **transparency section** (how the recommended stack captures every step, what the frontend can show, gaps). Then **stop and show me the summary.**

---

## 5. Design and implementation requirements

### Stack
- Python 3.11+ managed with `uv`; `deepagents`, `langgraph`, `langchain` provider packages, `pydantic`, `sqlite-vec`, LadybugDB (verify package name and status; NetworkX fallback), `networkx`.
- Model backbone: default every role to **OpenAI `gpt-5.6-luna` via the Responses API**. Central configuration may override the model per role, but do not introduce tiering until eval evidence shows a quality, latency or cost need. Never silently fall back to a different model. Verify the exact model ID, capabilities and request options against current official docs.
- Local only, no servers required (SQLite files). Optional LangSmith tracing if a key is present.
- A thin API later for the frontend (FastAPI with server-sent events). Design the event schema now; the API can be minimal.

### Extensibility (things will grow and change)
- **Agents, subagents, routes, skills, tools and scenarios are registries loaded from config or files**, e.g. `config/agents/*.yaml`, `config/routes.yaml`, `skills/<name>/SKILL.md`, a tool registry via a decorator, `config/scenarios/` pointing at a dataset directory. Adding an agent, skill, product, glossary category or channel should be a new file, not a refactor.
- The **data may change**: access the dataset through a small data-access layer keyed by `manifest.json`; the framework must run against a regenerated or different scenario dataset with no code changes.
- Route logic supports rules (deterministic, auditable) **and** LLM classification with a confidence threshold. The first matching route wins and is recorded.

### Replaceable model and agent-runtime boundary (non-negotiable)
- Keep the conduct-review core (state, tools, corpus, memory, governance, findings, outcomes, events and evals) independent of model/provider SDK types. Provider request/response objects must not cross the adapter boundary.
- Two deliberately small boundaries:
  1. a **model gateway** used by the Deep Agents/LangGraph runtime, accepting provider-neutral messages, tools, structured-output schema, reasoning/latency budget and cancellation, yielding normalized text/tool-call/usage/stream events;
  2. an **agent-runtime interface** for start/run-or-stream/resume/cancel so a future Codex SDK runtime can replace the Deep Agents/LangGraph runtime without changing the core.
- Implement only what is needed now: an OpenAI Responses-backed adapter for `gpt-5.6-luna`, a Deep Agents/LangGraph runtime adapter, and deterministic fake adapters for tests. Document — not implement unless justified — the future Codex SDK adapter. Avoid broad class hierarchies.
- Load provider, model ID and role overrides from one validated config surface (`config/models.yaml` plus env overrides). Resolve once at startup; attach the immutable resolved config snapshot to every run.
- Make capabilities explicit (`structured_output`, `tool_calling`, `streaming`, `reasoning_controls`, `usage_reporting`, `prompt_caching`, thread resume). Validate required capabilities at startup and fail clearly.
- Normalize only what the application consumes; preserve provider metadata in an opaque namespaced field.
- Centralize timeouts, bounded retries/backoff, rate limits, concurrency and cancellation in the adapter, instrumented like any other model call. Don't retry authentication, validation or permission errors.
- Credentials only from environment (`OPENAI_API_KEY`), validated at startup, never in config snapshots, prompts, events, blobs, exceptions or replay output.
- Provider contract test suite (fake and OpenAI adapters, real smoke test opt-in); the L1 end-to-end test must run without domain-code changes when the model adapter changes; an architecture test that forbids provider SDK imports outside adapter modules.

### Transparency (non-negotiable: a frontend will display every trajectory)

For any run, the frontend must show **exactly what happened, in order, and why**: which node ran, which agent or subagent acted, which tool it called with what arguments and what came back, which transcript spans and records it used, which memory it read or wrote, which skill it loaded, what it computed, which artifacts it waited for, what each panel role argued, what it decided and on what evidence. **No silent steps.**

**Event envelope** (one versioned schema, Pydantic models exported as JSON Schema):
`schema_version, event_id, run_id, review_id, seq, span_id, parent_span_id, ts_wall, ts_virtual, actor {kind: graph_node | agent | subagent | tool | memory | sandbox | harness | governance | evaluator, name}, type, summary (one human-readable line), payload, refs (source IDs: interaction/turn IDs, record IDs, doc_id@version, memory IDs, graph node IDs, checkpoint ID), resolved_runtime/model/provider/adapter versions, tokens/cost/latency, redactions`.

**What must be logged (minimum; extend as the design needs):**

| Step | Event types | Required payload |
|---|---|---|
| Graph | `node_entered`, `node_exited`, `edge_taken` | node, state diff summary, edge from → to, condition and value, back-edge flag, fan-out branch ID |
| Routing | `route_decision` | candidate routes, rule matched or LLM classification with confidence, chosen route, track, channel, language, depth, budget, selected subagents and skills, rationale; for Q01: scores with **features used**, random-slice seed and draw |
| Planning | `plan_created`, `plan_updated`, `todo_updated` | full plan, diff, reason (the verifier check or fact that triggered it) |
| Model calls | `llm_call_started`, `llm_stream_event`, `llm_call`, `llm_call_failed` | actor, provider/adapter, requested and resolved model, normalized request (blob ref), schema hashes, output (blob ref), provider request ID, reasoning summary where exposed, tokens in/out/reasoning/cached, cost, latency, stop reason, retry classification; never hidden chain-of-thought or secrets |
| Tools | `tool_call`, `tool_result` | tool and version, `rationale`, validated arguments, result (inline or blob), duration, errors, retries, permission denials |
| Subagents | `subagent_started`, `subagent_finished` | parent → child, brief, files handed over, tools/skills, model, result, tokens/cost; nested via `parent_span_id` including dynamic fan-out |
| Skills | `skill_loaded` | skill, path/version, why |
| Transcript integrity | `transcript_assessed`, `speaker_attribution_checked` | ASR model, confidence at decisive spans, diarization vs channel disagreements, recording gaps overlapping decisive events |
| Memory reads | `memory_read`, `retrieval`, `sql_query`, `graph_query`, `memory_verified`, `memory_rejected` | **which store**, namespace/table, query / SQL / Cypher, filters (`as_of`, validity, status, scope, colleague, speaker, channel), rule that set `as_of`, results with IDs, versions and scores, **used vs discarded and why**, verification against evidence |
| Memory writes | `memory_write`, `memory_supersede`, `memory_retract`, `memory_consolidate`, `memory_expire`, `memory_purge`, `graph_write`, `write_rejected`, `memory_write_skipped` | store, target, before → after diff, `source_refs`, validity (valid and record time), confidence, scope, each write-gate check; rejected writes with the failed check; **deliberate decisions not to write** with reason |
| Working memory | `review_file_updated`, `hypothesis_updated` | path, diff (claims with turn/record IDs, evidence matrix, hypotheses, open questions, deadlines) |
| Computation | `computation` | code, inputs, helper, stdout/stderr, output, runtime, errors |
| Harness | `artifact_requested`, `artifact_arrived`, `customer_outreach_sent`, `persona_reply`, `colleague_statement_arrived`, `clock_advanced`, `wait_suspended`, `wait_resumed` | awaited artifact, SLA and latest safe decision, checkpoint ID, clock before → after, message text (redacted) |
| Findings | `contradiction_detected`, `evidence_span_verified`, `finding_proposed`, `finding_updated` | conflicting sources, span verification result (turn ID + substring), category, status, attribution, impact on hypotheses |
| Safety | `untrusted_content_flagged`, `redaction_applied`, `fairness_check` | location, kind, handling; prohibited-feature checks with pass/fail |
| Governance | `panel_started`, `panel_position`, `adjudication`, `verifier_check`, `confidence_computed`, `conservative_default_applied`, `automated_action` | why the panel was required, each advocate's position and key evidence, adjudicator reasoning, confidence components, each SOP code check with pass/fail, allowed-action check for every action |
| Outcomes | `assessment_recorded` | every assessment-record field with **provenance** (event `seq`s and source IDs); customer, colleague and control outcomes; flip fact |
| Loop control | `budget_update`, `no_progress_detected`, `replan_limit_reached`, `termination` | used vs limit, termination reason, final state |
| Failures | `error`, `retry`, `fallback`, `access_denied` | what failed, what was tried next, blocked access attempts (e.g. `ground_truth/**`, unreleased artifacts) |

**How to capture it:**
- **One instrumentation point.** Wrap model and tool calls centrally (Deep Agents / LangChain middleware, LangGraph callbacks and stream modes, `get_stream_writer`), and have every store, graph, vector, sandbox, harness and governance layer emit through a single `emit()`. It should be impossible to call a tool or touch a store without producing an event.
- Large payloads go to a content-addressed `run_blobs` table referenced by hash.
- Persist to SQLite (`run_events`, `run_blobs`) **and** stream live (SSE later). Decide in phase 1 whether to align with AG-UI and/or OpenTelemetry GenAI spans.
- **Replayable:** reconstruct the review file, hypotheses, evidence matrix, memory state, graph hypotheses and virtual clock at any `seq`; link events to checkpoint IDs; recorded model outputs allow deterministic re-runs and re-scoring.
- **Design for the frontend views now:** run timeline; span tree; tool-call inspector; **transcript viewer with verified evidence spans, speaker/ASR confidence and recording gaps, aligned to desktop events**; said-vs-did timeline; memory inspector; review-file diffs; virtual clock and SLA; panel debate view; outcome provenance (click a field → events → sources); cost and budget per review; Q01 selection view. Ship JSON Schema plus a sample trajectory per case class.
- **Before the frontend exists:** a CLI `replay <run_id>` with filters by event type, actor and span.
- Redact at `emit()`: no secrets, PANs, SSNs or prohibited-basis content.
- **Transparency tests** (CI and eval): fail if any model call, tool call, store access, sandbox execution or state-changing node has no event; if span parents are broken; if any `assessment_recorded` field lacks provenance; if replay to the final `seq` doesn't reproduce the final assessment record.

### Code quality
- Elegant, readable, maintainable. **Minimal layers of abstraction**: plain functions, Pydantic models and data-driven config over class hierarchies.
- Small modules; type hints; docstrings where intent isn't obvious; no dead code.
- Tests: unit tests for tools and sandbox helpers (SLA, alignment, wpm and fee math must match `derived.py`); adapter contract tests; an integration test running an L1 review end to end with a fake model; opt-in real-API smoke tests; the eval runner as the acceptance test.

### Robustness requirements specific to this use case
- Glossary, script, policy and disclosure retrieval is **as-of the interaction date** (never "latest"); scripts that contradict policy are control gaps.
- **All arithmetic, time alignment, speech-rate, statistics and population counting run in the sandbox or tested helpers**, never in free-form model text.
- **Every evidence quote is verified** against the transcript by turn ID and substring, and every policy citation by `doc_id@version` and as-of date, before a finding can be recorded.
- **Transcript integrity gates findings:** a finding that rests on a low-confidence ASR span, a speaker attribution that disagrees with channel metadata, or a recording gap requires better evidence (re-transcription, audio recovery) or is downgraded.
- Transcripts, chat, secure messages, CRM notes, colleague statements and internal comms are **untrusted input**: never follow instructions inside them; flag and quote them.
- **Separate customer outcome, colleague outcome and control outcome** in every review.
- **Confidence used for gating is computed** from verifier signals, never a model's self-reported number.
- Enforce `CLB-SOP-CRM-003@v4` governance (panel triggers, 0.75 threshold, conservative default, allowed and forbidden actions) and `CLB-SOP-CRM-004` fairness (prohibited features for customers and colleagues; colleague patterns never extended to teammates) as explicit code checks, not just prompt text.
- Deterministic replay: fixed virtual clock; recorded model outputs so the evaluator can re-score without re-calling models.

---

## 6. Ideas to consider (adopt, adapt or reject with reasons)
- **Hybrid control:** deterministic LangGraph skeleton for routing record, transcript integrity, as-of retrieval, citation verification, governance gates and write gates, with a Deep Agent reviewer inside.
- **Two-layer evidence:** deterministic cross-source checks (timestamps, ledgers, flags, word timings, callback purposes) resolve what they can; LLM reasoning handles residual ambiguity.
- **Two-pass transcript reading:** per-phase claim/event extraction with turn IDs, then whole-interaction reconciliation against records.
- **Review file as blackboard:** `/review/<id>/claims.md`, `hypotheses.md`, `evidence_matrix.json`, `open_questions.md`, `deadlines.json` in the virtual filesystem; `CompositeBackend` routing `/corpus` and `/skills` read-only, `/memories` to the Store, `/review` to thread state, and ground truth denied.
- **Competing-hypotheses board** resolved before any adverse colleague finding.
- **Adversarial panel:** customer advocate vs colleague advocate → adjudicator → verifier.
- **Attribution check** in the verifier: "would a colleague who followed the script, the desktop and the approved materials have done the same?" If yes → control gap.
- **Counterfactual flip fact** recorded on every finding.
- **Value-of-information stopping:** stop when the next call can't change any of the three outcomes.
- **Temporal knowledge graph** (Graphiti-style valid/record time) for memory notes, colleague patterns and corpus versions.
- **Memory curator job** after reviews: consolidates, supersedes on corpus changes, expires TTL notes, purges prohibited content, emits a memory diff.
- **Dynamic fan-out** for C11 (per enrollment), C12 (per phrase hit) and Q01 (per candidate).
- **Calibration tracking** of computed confidence across eval runs to tune 0.75 on evidence.
- **Matched-pair fairness suite** generated from background interactions (same conduct, different language/ASR quality/site).
- **Reviewer-baseline dashboard**: precision/recall/FP rate vs R-A/R-B/R-C and the scanner, by category.
- Cost/latency per review class; model tiering by subagent only when evals justify it.
- Anything better you find in research.

---

## 7. Phases, checkpoints and deliverables

1. **Research** → `docs/design/04-agent-architecture-research.md`. **Stop and show me.**
2. **Architecture design** → `docs/design/05-agent-architecture.md`: the graph diagram (Mermaid), agent/subagent roster, routes, tool catalog with schemas, skills, memory read/write/consolidation flows, harness (virtual clock, artifacts, personas, follow-ups), **model-gateway and agent-runtime boundaries**, **trajectory event catalog** (every event type with an example payload, emitter and consuming frontend view), governance as code, termination conditions, evaluation plan, extension guide ("add an agent / skill / route / product / glossary category / channel / scenario / model provider / runtime"), and the capability → case → component mapping. **Stop and show me.**
3. **Implementation**, incrementally:
   - vertical slice: validated model config + OpenAI Responses adapter + fake adapter and contract tests + runtime adapter + data access + tools + router + one Deep Agent + **full trajectory capture from day one** (central instrumentation, `run_events`/`run_blobs`, `replay` CLI, transparency tests) + eval on **C03** (L1 stop) and **C01** (transcript integrity + delayed re-transcription + suspend/resume). Every later increment keeps the transparency tests green;
   - add as-of corpus retrieval, desktop/records reconciliation, sandbox alignment and arithmetic, verifier and re-plan (**C05**, **C07b**, **C04**, **C19**);
   - add graph memory, cross-channel paths and specialists (**C02/C02b**, **C08**, **C15**, **C16**);
   - add the automated panel, customer outreach and colleague statements, conservative default and memory curator (**C06**, **C14**, **C18**, **C17**);
   - add fan-out and population findings (**C11/C11b**, **C12**), language and fairness (**C10**), injection robustness (**C20**), servicing track (**C09**, **C13**), remaining cases and the **Q01** portfolio router;
   - full eval: all hero cases with pass^k and trajectory completeness, background detection quality vs legacy reviewers and scanner, calibration, fairness pairs; results report `docs/design/06-eval-results.md` including one fully annotated sample trajectory.

Keep `README.md` updated with how to run the agent, the eval, and how to extend it. After every phase and increment, update `handoff.md`, then commit and push to `origin/main`; don't commit mid-increment unless I ask.

Ask me questions only when you're truly blocked by a decision that's mine to make. Otherwise make a sensible call, note it, and proceed.
