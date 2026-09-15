# ConductAI agent architecture research

**Status:** Stage 2 recommendation / Phase 1 checkpoint  
**Research date:** 15 September 2026  
**Scope:** architecture research for a fully automated, replayable credit-card conduct-review system built first on Deep Agents and LangGraph

## Executive conclusion

ConductAI should use a **hybrid deterministic compliance graph with a bounded agentic investigation core**:

1. A LangGraph state machine owns intake, routing, clocks, budgets, checkpoints, transcript-integrity gates, verifier gates, automated governance, actions, memory write gates, and termination.
2. One Deep Agent is the lead reviewer. It owns the review file and chooses which evidence to pursue, which registered specialist to invoke, and when a hypothesis or route must change.
3. Specialists run only when the route or evidence requires isolated context, distinct tools, or independent judgment. LangGraph `Send` provides bounded dynamic fan-out for C11, C12, and Q01; ordinary L1/L2 cases do not pay that coordination cost.
4. As-of selection, evidence-span and policy-citation verification, arithmetic, clock alignment, population counts, confidence calculation, fairness, permitted actions, and final-record completeness are deterministic code—not model assertions.
5. High-impact or uncertain findings go through the fully automated `CLB-SOP-CRM-003@v4` panel: independent customer and colleague advocates, adjudicator, verifier, computed confidence, and the conservative default. No product path waits for a human.
6. An application-owned, append-only event ledger is the audit source of truth. LangGraph event streams and checkpoints, LangSmith, AG-UI, and OpenTelemetry are inputs or projections, not substitutes for it.
7. The conduct core depends on two narrow neutral seams: a model gateway and an agent-runtime interface. OpenAI Responses with the exact `gpt-5.6-luna` model is the initial model implementation; a future Codex SDK implementation belongs at the runtime seam.

This is the same architectural family proven in CatcherAI, but the conduct domain makes four parts more load-bearing: transcript integrity, said-versus-did reconciliation, separate customer/colleague/control outcomes, and scope-safe pattern memory.

## Research method and evidence standard

The research combined:

- the ConductAI foundation, corpus and generated-data contracts, manifest, generator helpers, 23 hero reviews, Q01, and domain/AI-methods research;
- CatcherAI's architecture research, implemented architecture, evaluation results, and post-implementation lessons;
- current official documentation and source repositories for OpenAI, Deep Agents, LangGraph, AG-UI, LangSmith, LadybugDB, sqlite-vec, and memory projects;
- primary papers and project material for multi-agent design, regulatory retrieval, interactive-agent evaluation, memory, and safety;
- current contact-center product documentation as implementation-pattern evidence, not proof of autonomous adjudication quality.

The research did **not** inspect `data/generated/ground_truth/**`, `data/generated/simulation/**`, or unreleased `data/generated/on_request/**`. Those remain evaluator- or harness-only.

Claims use four evidence levels:

- **Proven interface:** present in current official documentation or source.
- **Evaluated practice:** supported by a benchmark or described evaluation, with limited external validity.
- **Pattern evidence:** an inspectable implementation or product behavior that informs design.
- **Marketing claim:** an assertion not strong enough to support an architectural guarantee.

## Findings that constrain the design

### 1. Conduct review needs a workflow around an agent, not one or the other

Anthropic distinguishes predefined workflows from model-directed agents and recommends adding agentic complexity only where it earns its cost.[^anthropic-effective] ConductAI needs both:

- routing, deadlines, as-of policy selection, confidence thresholds, action authorization, and termination must be predictable and testable;
- evidence pursuit, contradiction discovery, cross-channel traversal, root-cause revision, and value-of-information decisions benefit from adaptive reasoning.

A single unconstrained agent cannot prove that every integrity and governance gate ran. A fixed pipeline cannot anticipate that C06's fee question is really an undisclosed product change, or that C12's phrase search should pivot into a shared-material investigation. The boundary is therefore a deterministic graph around a lead investigator with bounded agency.

The review file should be a typed blackboard—plan, claims, evidence matrix, competing hypotheses, open questions, deadlines, budgets, and outcome drafts—not orchestration chat. This gives specialists a stable contract and makes every re-plan diffable.

### 2. More agents help only where decomposition is real

Anthropic reports strong gains for breadth-first multi-agent research, but also roughly 15 times the token use of ordinary chat and poor fit where work is tightly coupled.[^anthropic-research] ConductAI should therefore fan out only work that is both independent and context-heavy:

- C11: one bounded linked-interaction review per enrollment;
- C12: one bounded review per candidate phrase hit, followed by a deterministic merge and source investigation;
- Q01: candidate evidence extraction in batches after deterministic permitted-feature scoring;
- panel cases: customer and colleague advocates operate independently from the same frozen review-file snapshot.

Route selection, shared-state ownership, evidence merge, policy precedence, attribution, governance, and final decisions remain centralized. Specialists return typed artifacts with source IDs; they do not hand authority to each other.

Deep Agents' synchronous `SubAgent` and `CompiledSubAgent` surfaces provide context isolation and structured responses. Custom subagents do not inherit skills automatically, which is desirable here: each role gets an explicit skill and tool allow-list.[^deepagents-subagents] Deep Agents also has async subagents, but they run as independent Agent Protocol threads through in-process ASGI or HTTP server transports.[^deepagents-async] That is useful for interactive hosted systems, but it adds a server/runtime control plane that conflicts with ConductAI's initial local-only requirement.

For the POC, bounded parallelism should use LangGraph `Send`, which creates runtime map branches for an unknown number of inputs, with typed reducers for merging results.[^langgraph-graph-api] Registered Deep Agent specialists can execute inside those branches. This is easier to replay, cap, and replace than letting a supervisor create unconstrained roles.

### 3. Current Deep Agents APIs fit the inner loop, with version and security caveats

**Proven interface.** Current Deep Agents exposes `create_deep_agent` with model, tools, system prompt, middleware, subagents, skills, memory, response format, backend, checkpointer, and store extension points. Backends include state, filesystem/local shell, store, sandbox, and composite routing.[^deepagents-customization][^deepagents-backends] Skills use `SKILL.md` progressive disclosure and may include scripts, though script execution requires an execution-capable backend.[^deepagents-skills]

The latest project release observed during this research was `deepagents==0.7.13`. The project remains pre-1.0 and explicitly warns that minor versions can contain breaking changes.[^deepagents-releases] Consequences:

- pin exact versions and lock them with `uv`;
- wrap Deep Agents behind `AgentRuntime` and adapter-owned construction;
- add contract tests for subagent registration, structured returns, middleware coverage, skills, and backends;
- upgrade intentionally, never through a floating dependency range.

Deep Agents' virtual filesystem is useful for `/review` working state and read-only skills, but it is not ConductAI's data-security boundary. Access to ground truth, simulation, unreleased artifacts, prohibited fields, raw SQLite, and action tools must be blocked in the data router, sandbox mounts, and capability-aware tool executor. A prompt or filesystem hint is insufficient.

`CompositeBackend` is still a useful ergonomic layer:

- `/review/**` → thread-scoped state backend;
- `/skills/**` → read-only authored skills;
- `/corpus/**` → read-only, as-of-aware view rather than raw files;
- `/memory/**` → no direct write access; all writes go through governed memory tools;
- all other paths denied by default.

### 4. Current LangGraph primitives cover the required topology and waits

LangGraph provides typed state, conditional edges, `Command` for state update plus routing, and `Send` for dynamic map/fan-out.[^langgraph-graph-api] Its persistence layer checkpoints state by thread, exposes history and time travel, and supports fault recovery.[^langgraph-persistence] These primitives directly cover:

- deterministic-first route selection and re-routing;
- verify → re-plan and reconcile → re-route back-edges;
- C11/C12/Q01 fan-out with deterministic reducers;
- checkpointed waits for re-transcription, audio recovery, colleague statements, customer replies, and scheduled follow-ups;
- bounded replay from recorded outputs.

`interrupt()` is described primarily for human input, but technically pauses for any external input. ConductAI may use it only as a generic suspension primitive for harness-controlled external events—never approvals. On resume, LangGraph restarts the node containing the interrupt from its beginning, so each wait must be a dedicated node and all operations before it must be idempotent.[^langgraph-interrupts] Prefer an outbox/request node that commits an idempotency key, followed by a pure wait node.

Current LangGraph documentation recommends typed event streaming introduced in v1.2; the stream-mode surface also exposes `updates`, `values`, `messages`, `custom`, `checkpoints`, `tasks`, and `debug`, plus nested subgraph namespaces and `get_stream_writer()`.[^langgraph-streaming] These are excellent instrumentation inputs, but they do not prove every domain-store access or authorization result and do not replace the canonical ledger.

### 5. OpenAI fits behind a narrow model gateway

The official model page confirms the exact `gpt-5.6-luna` identifier. It supports the Responses endpoint, function calling, structured outputs, streaming, reasoning tokens, and `reasoning.effort` values from `none` through `max`; it has a 1,050,000-token context window and 128,000 maximum output tokens.[^openai-luna] It accepts text and image input but not audio, which is acceptable because ConductAI consumes transcript and recording-quality metadata rather than raw audio in the POC.

The model gateway should normalize only application-consumed semantics:

- provider-neutral messages and content blocks;
- JSON-schema tools and structured-output schema;
- normalized text, tool calls, usage, stop/error class, latency, provider request ID, and stream events;
- requested versus resolved model and reasoning budget;
- cancellation, bounded retries, rate limiting, and prompt-cache usage.

OpenAI request/response classes, LangChain message types, and provider errors must stop at the adapter. The immutable resolved runtime snapshot belongs on every run. Authentication, validation, and permission errors are terminal; only transient classes receive bounded retry with logged attempts.

The official model page currently lists only the alias, not a date-stamped Luna snapshot. ConductAI should therefore record the exact alias and adapter/package versions on every call, retain normalized model outputs for replay, and switch to a dated snapshot only when OpenAI publishes one and evaluation approves it.

The Codex SDK is structurally an agent runtime rather than a chat-model adapter. The current official documentation offers a stable Python `openai-codex` library that controls a local app-server over JSON-RPC and supports starting and resuming threads; TypeScript provides the same thread lifecycle.[^codex-sdk] A future Codex integration should implement `start`, `run_or_stream`, `resume`, and `cancel` at the `AgentRuntime` boundary and map item events into ConductAI's ledger. It should not be squeezed into a `BaseChatModel` facade.

### 6. Three memory planes are necessary, but memory is never evidence by itself

The cases require three different query semantics:

| Plane | POC implementation | What it is authoritative for |
|---|---|---|
| Persistent | SQLite + FTS5 + LangGraph SQLite checkpointer | exact records, review state, lifecycle state, events, checkpoints |
| Semantic | sqlite-vec plus FTS5 hybrid retrieval | candidate corpus chunks, transcript segments, precedents, complaints, notes |
| Graph | LadybugDB embedded Cypher, NetworkX fallback | multi-hop relationships and scoped hypothesis edges |

`sqlite-vec` is installable as `sqlite-vec`, supports vector virtual tables and metadata/partition columns, and remains pre-v1.[^sqlite-vec] Its pre-v1 status means pinning and contract tests are mandatory. Effective-date/status filters should be applied in SQL before or alongside vector ranking; vector similarity must never choose a policy version on its own.

LadybugDB's official Python package is `ladybug`; it is embedded and exposes Cypher through client APIs.[^ladybug-install][^ladybug-cypher] The recent project rename and evolving releases justify the already-planned small graph interface and NetworkX fallback. Backend selection and any fallback must be explicit run events, not silent behavior.

Graphiti supplies the most useful conceptual memory pattern: changing facts retain source provenance and separate fact-valid time from ingestion/record time.[^graphiti] ConductAI should borrow this bitemporal model, not Graphiti's full ingestion stack. Policy versions and memory lifecycle are already structured; model-extracted graph mutations would add avoidable nondeterminism.

LangMem distinguishes semantic, episodic, and procedural memory and supports background extraction/consolidation.[^langmem] Its APIs may help implement the curator, but Copperlake's write gate remains authoritative because generic memory managers do not enforce colleague scope, prohibited-feature purging, source verification, or `CLB-SOP-CRM-005@v2` lifecycle states.

The safe read flow is:

1. construct a scope from review ID, interaction, colleague, product, route, speaker/channel, interaction date, validity, status, and confidence;
2. retrieve exact/FTS/vector/graph candidates and log all filters and IDs;
3. mark used versus discarded candidates with reasons;
4. treat memory and precedent as leads;
5. verify every load-bearing claim against primary evidence and as-of corpus text.

The safe write flow is propose → schema check → source verification → fairness/scope check → dedupe/conflict check → lifecycle operation → transactional write → index/graph projection → event. `skip` and `reject` are first-class results. C11b's deliberate non-write and C14's purge are as important as C11's pattern write.

### 7. Evidence reliability must be layered, not delegated to a judge prompt

Regulatory retrieval benefits from combining lexical and neural retrieval, but RIRAG/ObliQA evaluates legal question answering, not autonomous financial action.[^rirag] ConductAI should borrow hybrid retrieval while retaining deterministic date/status filters and clause verification.

The lead reviewer should use a two-pass evidence pattern:

1. **Extraction:** phase- or turn-level claims and candidate events with exact turn/record IDs, no verdict.
2. **Reconciliation:** said versus did versus recorded, with clock-corrected event alignment, contradictions, policy applicability, and alternative hypotheses.

All quotes are verified by turn ID plus substring; all policy citations by `doc_id@version`, clause, and interaction date; all arithmetic and time alignment by tested helpers through the sandbox. Low-confidence decisive words, speaker/channel disagreement, or a recording gap trigger better evidence or downgrade—not a model instruction to “be careful.”

Computed confidence is a policy artifact derived from verifier pass rate, citation verification, decisive-fact coverage, transcript quality at decisive spans, and panel agreement. Self-reported model confidence may be observed for analysis but never gates a colleague outcome.

The verifier-critic loop should be bounded: verify once, produce typed failed checks, re-plan only if a failed check can change an outcome, and cap re-plans by route. The stop rule is not “the model feels done”; it is one of the explicit termination conditions.

Reflexion and Self-Refine show that structured feedback can improve a later attempt, but neither makes the feedback correct.[^reflexion][^self-refine] ConductAI should borrow the bounded critique/revision pattern, not free-form self-approval or automatic promotion of reflective prose into memory. A failed verifier check must name the missing or contradictory source; a re-plan must address that check; a second unchanged failure terminates or downgrades rather than looping.

Conformal or selective-prediction techniques are promising for calibrating an abstention/default boundary, but the POC's 23 hand-built cases are too small and deliberately non-i.i.d. to justify a formal coverage claim. Stage 5 should report reliability curves, Brier score, expected calibration error, risk/coverage, and threshold sensitivity. The coded 0.75 policy threshold remains authoritative unless a future representative calibration set supports a formally reviewed change.

Evaluation must inspect state transitions and executed actions, not only final prose. A “corrupt success”—the right assessment reached through leaked labels, prohibited features, an unverified quote, missing capability use, or an unauthorized write—is a failed run. This follows the tool-agent benchmark lesson that environment state and policy compliance provide stronger truth than an answer-style judge.[^taubench]

### 8. The harness is part of correctness, not test scaffolding

τ²-bench shows why interactive tasks differ from static question answering: the user and agent can both affect a shared world, and coordination failures must be separated from reasoning failures.[^tau2] ConductAI's customer replies, colleague statements, artifact arrivals, and scheduled actions need the same stateful treatment.

The harness must own:

- fixed virtual clock and `available_at` gating;
- scenario isolation and deny rules;
- idempotent artifact requests and releases;
- persona-driven customer replies and colleague statements;
- SLA-derived latest safe decision time;
- budgets, cancellation, resume, and recorded model outputs;
- background and hero evaluation without exposing labels to the runtime.

Suspension is allowed only for an external event. If the event cannot arrive before the latest safe decision time, the graph resumes at that time and decides using the appropriate insufficient-evidence or conservative-default path.

### 9. Contact-center products validate useful patterns, not autonomous trust

Amazon Connect's current automated evaluation design is informative: evaluation forms are versioned, questions can be conditional, complex criteria should be split, the selected form language should match its content, and rules select which contacts receive which evaluation.[^aws-evaluation] It also recommends generative evaluation mainly where the transcript contains the needed evidence. ConductAI should borrow versioned rubrics, route-specific criteria, conditional questions, and explicit selection rules.

ConductAI must go beyond that pattern because its decisive evidence often lives outside the transcript: desktop events, offer/enrollment records, policy versions, callbacks, preferences, complaints, incidents, and later artifacts. Vendor claims or scorecards are not acceptance evidence for fully automated remediation or colleague findings.

The stronger product comparison is architectural:

- conventional QA systems organize work around forms and contact selection;
- ConductAI organizes work around a case file, evidence graph, three independent outcomes, governance, and replayable execution;
- version pinning is essential: even Amazon exposes specific versus automatically updated GenAI evaluation versions, which supports recording an immutable runtime/model snapshot.[^aws-evaluation-forms]

### 10. Prompt injection and fairness require code-enforced capability boundaries

OWASP notes that models do not reliably segregate instructions from external data and recommends separating untrusted content, least privilege, and code-enforced tool access.[^owasp-injection] In ConductAI, every transcript, chat, secure message, CRM note, colleague statement, complaint narrative, and internal message is untrusted evidence.

The system should:

- label untrusted content in typed content blocks and never concatenate it into system instructions;
- expose evidence-reading roles only to read tools;
- validate actor, route, review, target, and action against a capability matrix after every model tool proposal;
- keep remediation/action tools out of investigator contexts and expose them only to the deterministic action node;
- deny raw filesystem/database/network access from the compute sandbox;
- log attempted monitor-directed instructions and blocked access;
- redact secrets and prohibited content before prompts, events, blobs, errors, or optional telemetry.

Because the product has no human approval path, least privilege and deterministic authorization are the compensating controls. `CLB-SOP-CRM-004@v2` fairness checks must run at selection, retrieval, reasoning inputs, findings, graph/memory writes, and actions. Language and ASR quality are permitted only for evidence-quality/routing purposes, never risk or fault scoring. Team membership may locate shared material but cannot serve as evidence against a teammate.

## Candidate architectures

### Candidate A — deterministic LangGraph pipeline with one Deep Agent node

**Shape:** intake → route → integrity → one reviewer → verify → govern → act → memory → terminate.

**Strengths**

- smallest runtime and coordination surface;
- easy checkpointing, budgets, early exit, and deterministic tests;
- strong fit for C01–C05, C07/C07b, C09, C13, C16, C17, C20;
- cheapest path for the 96.4% clean background population.

**Weaknesses**

- one context becomes polluted by C11's 23 enrollment calls and C12's phrase population;
- opposing panel positions are not independent;
- tool visibility becomes broad unless the single agent is repeatedly reconfigured;
- weak evidence that “subagents” are genuinely load-bearing.

**Verdict:** retain its explicit graph and early-stop discipline, but it cannot meet the full case catalog alone.

### Candidate B — Deep Agent supervisor with a fixed specialist team

**Shape:** supervisor owns the task list and delegates transcript, records, policy, population, remediation, panel, verifier, and memory work through the `task` tool.

**Strengths**

- context isolation and role-specific skills/tools;
- easy to extend through role files;
- strong fit for C06, C11, C12, C14 and panel independence;
- Deep Agents supplies planning, subagents, skills, middleware, and working-filesystem ergonomics.

**Weaknesses**

- the model can omit a mandatory gate or over-delegate a simple case;
- framework task history is not a financial audit ledger;
- global state merge, fan-out caps, deadlines, and termination become prompt-dependent;
- a fixed team encourages calling every role on every case.

**Verdict:** borrow registered specialists and structured returns, but do not give the supervisor control of compliance flow.

### Candidate C — deterministic compliance graph with selective specialists (recommended)

**Shape:** LangGraph owns the outer lifecycle. A lead Deep Agent owns investigation and the review file. Rules select mandatory nodes/skills; the lead requests optional evidence and specialists; `Send` fans out bounded work; deterministic reducers merge typed outputs; verifier and governance code control outcomes and actions.

**Strengths**

- explicit proof that every mandatory gate and termination rule ran;
- adaptive evidence pursuit without model-controlled authorization;
- cheap L1 path and scalable L4 fan-out;
- independent advocate positions and a frozen panel input;
- direct fit for all primary-capability cases;
- preserves provider/runtime replaceability.

**Weaknesses**

- more integration work than A or B;
- state schemas and reducers must be designed carefully;
- parallel event ordering and idempotent resume need first-class tests;
- two orchestration layers can duplicate behavior if boundaries are vague.

**Verdict:** adopt. Phase 3 design must make the boundary crisp: the graph decides *which obligations exist*; agents decide *how to investigate unresolved obligations*.

### Candidate D — event-sourced blackboard with peer agents and dynamic work stealing

**Shape:** peer agents subscribe to blackboard facts/events, claim tasks, write hypotheses, and converge through an adjudication protocol.

**Strengths**

- naturally parallel and visually impressive;
- every artifact can be represented as an event;
- flexible for large populations and future continuous monitoring.

**Weaknesses**

- conflict resolution, duplicate work, starvation, and termination become difficult;
- peers can amplify correlated errors or overwrite shared state;
- authority and scope are harder to explain to an auditor;
- unnecessary for 23 hero cases and a 6,527-interaction POC;
- hosted async subagents would violate the initial local-only constraint.

**Verdict:** borrow the append-only blackboard and event-sourced artifacts, not decentralized authority or work stealing.

## Recommended combination

Adopt Candidate C, borrowing:

- Candidate A's explicit state machine, route budgets, and early termination;
- Candidate B's registered context-isolated specialists, skills, and typed responses;
- Candidate D's append-only blackboard/event model and branch attribution, but not peer authority;
- CatcherAI's provider/runtime seams, canonical event envelope, emitter/blob store, hash chain, replay, governance-as-code structure, and trajectory evaluator.

### Recommended role registry

Use **12 role definitions**, not 12 agents on every run. Only the lead is universal; instances of the linked-interaction role fan out when needed.

| Role | Invoked when | Responsibility and boundary |
|---|---|---|
| Lead conduct reviewer | every non-trivial review | owns plan, hypotheses, open questions, evidence pursuit, route-change proposals; cannot authorize actions |
| Transcript-integrity analyst | phone quality issue, language mismatch, gap, low decisive confidence, speaker conflict | assesses ASR/diarization/gaps and requests better evidence; read-only |
| Desktop/records reconciler | speech and system actions can diverge | produces clock-corrected said/did/recorded matrix; computations through sandbox |
| Policy analyst | rule or product term is disputed/version-sensitive | returns as-of clauses, precedence, script-policy conflicts; no verdict |
| Linked-interaction reviewer | C11/C12/Q01 fan-out | bounded review of one interaction/candidate with typed evidence; no cross-entity inference |
| Population/pattern analyst | possible colleague/system/material population | graph traversal plus sandbox counts; enforces colleague/team scope boundary |
| Remediation planner | harm, customer choice, or multi-step restoration | proposes customer-safe actions and waits; action node re-authorizes |
| Customer advocate | panel only | strongest evidence-based customer/harm position from frozen review file |
| Colleague advocate | panel only | strongest evidence-based no-fault/control/insufficient-evidence position |
| Adjudicator | panel only | resolves advocate positions and records flip fact; cannot bypass verifier |
| Verifier | L3/L4 and panel cases; deterministic verifier runs every case | challenges coverage/attribution and emits typed failed checks; code independently verifies spans, citations, calculations, fairness, and actions |
| Memory curator | in-review when material; offline maintenance job | proposes/executes governed lifecycle operations through write gate; cannot alter case evidence |

Why no separate language agent: multilingual routing is a skill plus transcript-integrity specialization, and the facts are still assessed under the same policy and evidence contract. Why no separate “sales” and “servicing” supervisors: routes and skills provide that specialization without duplicating authority. Why no free-form general-purpose subagent: every production role needs an explicit tool, skill, response, budget, and permission contract.

### Invocation policy by depth

| Depth | Default shape |
|---|---|
| L1 | deterministic intake/route/integrity; lead only if rule evidence is not already conclusive; deterministic verifier; early termination |
| L2 | lead plus at most one investigation specialist; no population expansion without a discovered trigger |
| L3 | lead plus relevant integrity/records/policy/remediation roles; agent verifier when attribution or evidence is judgmental |
| L4 | lead, bounded parallel specialists, population fan-out if required, panel when coded predicate fires, full verifier and memory curator |
| Q01 | deterministic permitted-feature ranking and seeded stratified random slice; bounded linked-interaction extraction only where a feature needs evidence confirmation |

### Case-driven fit

| Architecture need | Forcing cases | Recommended mechanism |
|---|---|---|
| integrity wait/recovery | C01, C10, C12, C18 | integrity node/analyst → idempotent artifact request → dedicated wait → resume |
| cheap true-negative exit | C03 | rule-first L1 route + verified policy/record match + explicit `assessment_complete` termination |
| route/root-cause pivot | C04, C06 | typed contradiction/hypothesis update → `Command`/conditional back-edge → logged re-plan |
| said versus did and clocks | C05, C07b, C16, C20 | records reconciler + restricted sandbox helpers + exact source refs |
| cross-channel/graph traversal | C02/C02b, C08, C15 | scoped graph queries plus persistent-record verification |
| colleague pattern | C11/C11b | `Send` one interaction per branch; deterministic reducer; colleague-only graph write or logged non-write |
| shared material and diarization trap | C12 | speaker/channel-filtered hybrid search, branch review, material-source traversal, integrity gate |
| uncertain vulnerability | C14 | prohibited-feature purge, independent panel, computed confidence, conservative default |
| external customer choice | C06, C15, C17, C18 | remediation planner, persona harness, wait/resume, latest-safe-time rule |
| stale/overgeneral memory | C04, C07, C19 | as-of source verification and memory lifecycle gate |
| weekly low-prevalence selection | Q01 | deterministic scoring with permitted features + protected seeded random slice + trajectory audit |

## Reliability and automated governance

### Investigation loop

The lead loop is bounded by explicit obligations and progress:

1. read current review file and unresolved verifier checks;
2. choose one evidence action with a rationale and expected decision impact;
3. execute through a typed tool or registered specialist;
4. update claims, contradictions, hypotheses, evidence matrix, and budgets;
5. re-route/re-plan only when a new fact changes scope or root cause;
6. stop when all outcome-changing questions are resolved or the next evidence cannot arrive/change an outcome.

Every iteration records evidence novelty. Repeating an equivalent query with no new source IDs increments no-progress. Termination reasons are a closed enum: `assessment_complete`, `early_clean_exit`, `waiting_external_event`, `latest_safe_decision`, `budget_exhausted`, `no_progress`, `replan_limit`, `conservative_default`, `cancelled`, or `error_terminal`.

### Governance flow

1. Lead produces proposed findings and separate customer, colleague, and control drafts.
2. Deterministic pre-verifier checks exact spans, citations, as-of selection, calculations, decisive-span quality, provenance, prohibited features, and action allow-list.
3. Failures that can change an outcome go to one bounded re-plan; non-recoverable failures downgrade the affected finding.
4. Code evaluates the `CLB-SOP-CRM-003@v4` panel predicate.
5. If triggered, advocates receive the same frozen, redacted review-file snapshot and cannot see one another's positions.
6. Adjudicator resolves the typed positions and records the minimum flip fact.
7. Code computes confidence from verifier signals; the verifier agent's prose or any role's self-score is not a component.
8. Below 0.75, no adverse colleague finding is allowed. Customer-protective remediation follows the separate harm/consent rule.
9. Action node re-checks every action against authorization and idempotency before execution.
10. Assessment and memory writes require field-level provenance.

This is not “LLM debate decides truth.” The panel produces independent structured evidence assessments; deterministic policy turns them into bounded outcomes.

## Transparency and frontend-ready trajectories

### Canonical record versus framework projections

The canonical record is a local SQLite append-only ledger plus content-addressed blobs. It uses the event envelope required by the kickoff prompt, adds a hash-chain field (`prev_event_hash`, `event_hash`), and allocates `seq` transactionally per run.

LangGraph streams are adapters into the ledger:

- typed runtime/event streams supply graph, message, task, checkpoint, and subgraph signals;
- `get_stream_writer()` carries application events from nodes and tools;
- Deep Agents/LangChain middleware captures agent, model, tool, and subagent lifecycle;
- domain data, graph, vector, memory, sandbox, harness, governance, and action services emit directly through the same application emitter.

Checkpoints are snapshots linked by ID. They support recovery and state inspection, but replay after a checkpoint may re-execute model and external calls. Recorded normalized outputs and deterministic replay adapters are therefore required.[^langgraph-persistence]

LangSmith remains optional operational telemetry. It has useful nested run/span structure and automatic model/tool/retriever capture, but retention and masking are operational policies, not ConductAI's immutable audit contract.[^langsmith-observability][^langsmith-masking] Export only redacted allow-listed data.

### Reuse from CatcherAI unchanged

Reuse the following structures, renaming domain vocabulary but not semantics:

- versioned Pydantic event envelope and discriminated event payloads;
- transactional event emitter, content-addressed `run_blobs`, redaction-at-emit, sequence allocation, and SHA-256 hash chain;
- span/parent-span discipline and branch IDs;
- model/tool/store/sandbox/harness instrumentation choke points;
- replay reader, hash-chain verification, event filters, and recorded-output adapters;
- immutable resolved runtime/config snapshot;
- field-provenance representation and transparency reconciliation tests;
- optional OTLP/LangSmith export mapper;
- runtime start/stream/resume/cancel contract and fake-model adapter pattern.

Do **not** reuse dispute routes, packet assumptions, Regulation E calculations, cardholder/network outcome semantics, network actions, or dispute-specific agents. ConductAI needs transcript integrity, desktop alignment, as-of sales/servicing rules, customer/colleague/control outcomes, conduct panel predicates, and governed colleague/material graph writes.

### One instrumentation spine

“One instrumentation point” means one event API plus mandatory choke points:

- graph construction wraps every node and condition to emit entry, exit, state diff, chosen edge, back-edge, branch, and checkpoint;
- the model gateway emits every provider attempt, stream, terminal response, error classification, retry, cancellation, usage, and latency;
- middleware brackets every lead/specialist invocation and tool proposal;
- one tool executor validates Pydantic input, actor capability, route/review scope, rationale, and result;
- data/vector/graph/memory interfaces cannot execute queries without an emitter;
- sandbox, harness, governance, and action repositories have no uninstrumented public path;
- assessment persistence rejects fields without event and source provenance;
- `emit()` validates, redacts, blobs large payloads, computes hashes, persists, and publishes to subscribers.

Architecture tests should forbid raw `sqlite3.connect`, Ladybug connections, subprocesses, provider imports, and direct filesystem reads outside approved modules. Runtime reconciliation tests compare actual call/access counters and state mutations to event pairs.

### AG-UI and OpenTelemetry

AG-UI now defines lifecycle, step, message, tool-call, state snapshot/delta, activity, reasoning-summary, and subagent events.[^agui-events] Map the ConductAI ledger outward:

- node lifecycle → `StepStarted` / `StepFinished`;
- tool calls → AG-UI tool-call lifecycle;
- review-file projection → `StateSnapshot` plus RFC 6902 `StateDelta`;
- plan/search/wait/panel activity → activity events;
- subagent invocation → subagent lifecycle;
- conduct-specific events → documented `Custom` events.

AG-UI is a frontend transport, not the canonical schema: it lacks as-of retrieval semantics, memory lifecycle, computed-confidence components, action authorization, and field provenance.

OpenTelemetry GenAI conventions offer portable model, agent, tool, and usage attributes, including cached and reasoning tokens, but several agent conventions remain under development.[^otel-genai] Keep a one-way exporter so standards changes do not reshape the ledger.

### Frontend views enabled

| View | Ledger requirements |
|---|---|
| run timeline | `seq`, wall/virtual time, actor, type, summary, status |
| span tree | span IDs, parents, agent/subagent/tool lifecycle, branch IDs |
| workflow graph | node enter/exit, edge condition/value, back-edge, checkpoint |
| transcript viewer | exact turns/words, evidence verification, ASR/speaker/channel confidence, gaps |
| said-versus-did timeline | clock-corrected transcript spans, desktop events, order/ledger records |
| tool inspector | rationale, validated args, result/blob, retries, authorization |
| retrieval/memory inspector | store, query, filters, candidates, used/discarded, verification, lifecycle diffs |
| review-file time travel | state snapshots/hashes and JSON Patch per sequence |
| clock/SLA view | requests, arrivals, waits, resumes, clock movement, latest safe time |
| panel debate | frozen input hash, independent positions, adjudication, verifier checks, flip fact |
| outcome provenance | click field → event sequences → source IDs/doc clauses |
| cost/budget | per-call usage/latency/cost and cumulative route budget |
| Q01 selection | permitted feature contributions, risk ranking, strata, random seed/draw |

### Transparency gaps and mitigations

| Gap | Mitigation |
|---|---|
| checkpoint replay re-calls nondeterministic dependencies | recorded model/tool/harness outputs and replay adapters |
| framework streams omit domain-store semantics | instrument application access interfaces and reconcile counters |
| resume re-runs the interrupted node | dedicated pure wait nodes; idempotent request/action keys |
| parallel branches race event order | transactional sequence allocation; branch-local state; deterministic reducer; merge event |
| hidden chain-of-thought is unavailable and inappropriate to log | concise model-provided rationale, plan diffs, evidence, hypotheses, checks, and flip facts |
| custom tools are outside Deep Agents filesystem permissions | capability-aware central executor and backend deny rules |
| Deep Agents is pre-1.0 | exact pins, adapter boundary, contract tests, evaluated upgrades |
| sqlite-vec is pre-v1 and Ladybug evolves | exact pins, startup probes, backend contract tests, explicit NetworkX fallback |
| optional telemetry can leak or expire | redact before export, allow-list fields, opt-in only; local ledger is authoritative |
| generic agent UI lacks conduct semantics | project AG-UI plus conduct-specific custom events; build the planned domain console later |

## Safety and audit implications

The Federal Reserve's April 2026 SR 26-2 supersedes SR 11-7 and emphasizes a risk-based approach tailored to model use and business risk.[^sr2602] ConductAI should therefore retain versioned configuration, conceptual design, validation evidence, performance monitoring, limitations, overrides/defaults, and outcome analysis. The POC is not a claim of regulatory compliance, but its ledger should make independent validation possible.

An examiner, internal auditor, model validator, customer-remediation reviewer, or colleague appeal process must be able to reconstruct:

- the exact input data visible at each virtual time and every denied source;
- governing corpus versions and the rule that selected them;
- model/provider/runtime/adapter versions, role/route/skill/tool registries, and budgets;
- every candidate retrieval result and why it was used or discarded;
- transcript-quality decisions, contradictions, calculations, and hypothesis changes;
- panel trigger, frozen input, independent positions, computed confidence, and conservative default;
- per-field source and event provenance;
- every authorized action, idempotency key, before/after state, and forbidden action check;
- every memory read, verification, write, supersession, retraction, consolidation, purge, rejection, and deliberate non-write.

Full transparency does not mean exposing hidden chain-of-thought or prohibited content. It means logging structured reasons and externally checkable evidence sufficient to reproduce the decision.

## What is established, promising, and unsafe to assume

| Finding | Evidence level | Design consequence |
|---|---|---|
| Current Deep Agents supports tools, registered subagents, skills, middleware, structured output, and composite backends | proven interface | use inside the graph; pin and wrap it |
| LangGraph supports typed state, conditional control, `Send`, checkpoints, waits/resume, and rich streaming | proven interface | use as deterministic outer runtime |
| `gpt-5.6-luna` supports Responses, tools, structured output, streaming, and reasoning controls | proven interface | implement first model adapter; record alias/version metadata |
| stable Python Codex SDK exposes local runtime threads and resume | proven interface | future adapter belongs at runtime seam |
| multi-agent breadth helps decomposable, high-value work at large token cost | evaluated practice | fan out C11/C12/Q01 and panels only |
| hybrid lexical/neural retrieval helps regulatory QA | evaluated practice | use hybrid retrieval, never omit deterministic date/source verification |
| temporal provenance improves changing-fact memory | evaluated system pattern | implement bitemporal note/edge lifecycle |
| contact-center automated QA forms and routing exist | pattern evidence | borrow versioned forms/routes, not autonomous-trust claims |
| model self-confidence is a calibrated adverse-action gate | not established | compute confidence from verifier evidence |
| framework tracing/checkpoints form a complete audit ledger | false | application ledger remains canonical |
| a swarm is inherently more advanced or accurate | unsupported | use bounded manager/worker topology |
| prompts can enforce data isolation, fairness, or action authorization | false | enforce in code and data/tool boundaries |

## Decisions for Stage 3 to specify

1. Exact LangGraph state schema, nodes, edges, reducers, checkpoint boundaries, wait protocol, and termination enum.
2. Route configuration schema and deterministic-first/LLM-threshold precedence for reviews and Q01.
3. Twelve-role registry, typed return contracts, per-role tools/skills, depth policies, budgets, and fan-out caps.
4. Provider-neutral model gateway and agent-runtime protocols, capability validation, retry/error taxonomy, and immutable resolved config.
5. Tool schemas, rationale field, actor/route/review capabilities, idempotency, and action authorization.
6. Data router deny rules, prohibited-field projections, untrusted-content representation, and sandbox isolation.
7. Persistent/vector/graph interfaces, bitemporal retrieval, note/edge lifecycle, and NetworkX fallback behavior.
8. Full event union, hash chain, blobs/redaction, checkpoint links, AG-UI/OTel projections, and replay CLI.
9. Governance predicates, advocate/adjudicator artifacts, verifier checks, confidence formula, allowed actions, and conservative defaults.
10. Evaluation plan for deterministic checks, trajectory completeness, capability × case use, pass^k, low-prevalence background quality, calibration, and fairness pairs.

## Sources

[^anthropic-effective]: Anthropic, [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents).
[^anthropic-research]: Anthropic, [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system).
[^deepagents-subagents]: LangChain, [Deep Agents: subagents](https://docs.langchain.com/oss/python/deepagents/subagents).
[^deepagents-async]: LangChain, [Deep Agents: async subagents](https://docs.langchain.com/oss/python/deepagents/async-subagents).
[^deepagents-customization]: LangChain, [Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization).
[^deepagents-backends]: LangChain, [Deep Agents: backends](https://docs.langchain.com/oss/python/deepagents/backends).
[^deepagents-skills]: LangChain, [Deep Agents: skills](https://docs.langchain.com/oss/python/deepagents/skills).
[^deepagents-releases]: LangChain, [Deep Agents releases](https://github.com/langchain-ai/deepagents/releases).
[^langgraph-graph-api]: LangChain, [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api).
[^langgraph-persistence]: LangChain, [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).
[^langgraph-interrupts]: LangChain, [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
[^langgraph-streaming]: LangChain, [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming).
[^openai-luna]: OpenAI, [GPT-5.6 Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
[^codex-sdk]: OpenAI, [Codex SDK](https://developers.openai.com/codex/sdk).
[^sqlite-vec]: Alex Garcia, [sqlite-vec](https://github.com/asg017/sqlite-vec).
[^ladybug-install]: LadybugDB, [Install Ladybug](https://docs.ladybugdb.com/installation/).
[^ladybug-cypher]: LadybugDB, [Query with Cypher](https://docs.ladybugdb.com/get-started/cypher-intro/).
[^graphiti]: Zep, [Graphiti temporal knowledge graph](https://github.com/getzep/graphiti).
[^langmem]: LangChain, [LangMem](https://langchain-ai.github.io/langmem/).
[^rirag]: Zhang et al., [RIRAG: a bi-directional retrieval-enhanced framework for financial legal QA](https://aclanthology.org/2025.regnlp-1.17/).
[^tau2]: Barres et al., [τ²-bench: evaluating conversational agents in a dual-control environment](https://arxiv.org/abs/2506.07982).
[^taubench]: Yao et al., [τ-bench: a benchmark for tool-agent-user interaction](https://arxiv.org/abs/2406.12045).
[^reflexion]: Shinn et al., [Reflexion: language agents with verbal reinforcement learning](https://arxiv.org/abs/2303.11366).
[^self-refine]: Madaan et al., [Self-Refine: iterative refinement with self-feedback](https://arxiv.org/abs/2303.17651).
[^aws-evaluation]: AWS, [Evaluate agent performance using generative AI](https://docs.aws.amazon.com/connect/latest/adminguide/generative-ai-performance-evaluations.html).
[^aws-evaluation-forms]: AWS, [Create an evaluation form](https://docs.aws.amazon.com/connect/latest/adminguide/create-evaluation-forms.html).
[^owasp-injection]: OWASP GenAI Security Project, [LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/).
[^agui-events]: AG-UI, [Events](https://docs.ag-ui.com/concepts/events).
[^otel-genai]: OpenTelemetry, [Generative AI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/).
[^langsmith-observability]: LangChain, [LangSmith observability concepts](https://docs.langchain.com/langsmith/observability-concepts).
[^langsmith-masking]: LangChain, [Prevent logging sensitive data in traces](https://docs.langchain.com/langsmith/mask-inputs-outputs).
[^sr2602]: Federal Reserve, [SR 26-2: revised guidance on model risk management](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.htm).
