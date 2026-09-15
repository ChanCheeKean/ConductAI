# ConductAI — an agentic conduct reviewer for credit-card servicing

ConductAI is a proof-of-concept **fully automated agent system that reviews credit-card customer-service interactions for sales and servicing misconduct**. It reads phone transcripts, chat logs and secure messages together with the systems of record a human reviewer would check — desktop activity, offers, enrollments, product changes, fee and rewards ledgers, account flags, preferences, callbacks, complaints — and the versioned rules that govern them: misconduct glossary, colleague scripts, policies, product disclosures and regulation. For every review it decides what happened to the customer, whether a colleague is at fault, and whether a script, system or piece of material failed — and it leaves a complete, replayable audit trail.

It follows the architecture and working method of its sibling project CatcherAI (Dispute Observatory): a synthetic world with hand-built hero cases and machine-checkable ground truth, a deterministic LangGraph skeleton around adaptive Deep Agents, three memory planes, a sandbox, a virtual-clock harness, automated governance instead of human review, and trajectory-first evaluation.

> **Status: Stage 3 architecture design complete.** The deterministic data foundation, corpus, ground truth, research recommendation, and implementation blueprint exist; the runtime has not yet been implemented. See [`handoff.md`](handoff.md) for the current checkpoint and next stage.

## Documents

| Document | Purpose |
|---|---|
| [`handoff.md`](handoff.md) | Current state, decisions, next steps, stage plan |
| [`docs/reference/reference-program-brief.md`](docs/reference/reference-program-brief.md) | The industry program this POC is inspired by (reference only) |
| [`docs/research/01-domain-research.md`](docs/research/01-domain-research.md) | Regulation, enforcement history, industry practice, AI-methods findings |
| [`docs/research/briefs/`](docs/research/briefs/) | Full cited research briefs behind 01 |
| [`docs/design/02-case-catalog.md`](docs/design/02-case-catalog.md) | 23 hero reviews + Q01 sweep: what each proves, expected path, ground truth, traps, capability coverage |
| [`docs/design/03-data-dictionary.md`](docs/design/03-data-dictionary.md) | Every file and field, joins, timestamps, output and ground-truth schemas, deliberate data-quality issues |
| [`docs/design/04-agent-architecture-research.md`](docs/design/04-agent-architecture-research.md) | Current framework/API research, candidate architectures, recommended hybrid and transparency design |
| [`docs/design/05-agent-architecture.md`](docs/design/05-agent-architecture.md) | Implementation blueprint: graph, roles, routes, tools, memory, harness, governance, event catalog, evaluation and extension contracts |
| [`docs/prompts/01-data-foundation-kickoff.md`](docs/prompts/01-data-foundation-kickoff.md) | Session prompt: build the corpus, generator, validator and ground truth |
| [`docs/prompts/02-implementation-kickoff.md`](docs/prompts/02-implementation-kickoff.md) | Session prompt: research, design and implement the agent system |

## Contents
1. [The use case](#1-the-use-case)
2. [Domain background](#2-domain-background)
3. [Example reviews](#3-example-reviews)
4. [The data ecosystem](#4-the-data-ecosystem)
5. [Relationships and review paths](#5-relationships-and-review-paths)
6. [Memory design](#6-memory-design)
7. [The evidence ecosystem](#7-the-evidence-ecosystem)
8. [The policy ecosystem and automated governance](#8-the-policy-ecosystem-and-automated-governance)
9. [How the dataset is generated](#9-how-the-dataset-is-generated)
10. [Architecture component → the scenario that forces it](#10-architecture-component--the-scenario-that-forces-it)
11. [Agent behavior this data enables](#11-agent-behavior-this-data-enables)
12. [Why this is a compelling demonstration](#12-why-this-is-a-compelling-demonstration)
13. [From POC to production](#13-from-poc-to-production)
14. [Target repository layout](#14-target-repository-layout)
15. [Assumptions, inventions, and open questions](#15-assumptions-inventions-and-open-questions)

---

## 1. The use case

### What we review
A colleague at **Copperlake Bank, N.A.** (a fictional US card issuer) handles a customer by phone, chat or secure message. Somewhere in that interaction a product may have been offered, a fee waived, a plan enrolled, a card changed, a complaint raised or a right mentioned. The system must decide:

- **Did anything reviewable happen?** Most interactions are clean. A flagged phrase can be accurate ("won't affect your credit" on a genuine soft inquiry), an outbound sale can be a customer-requested callback, and a scanner can be running last year's glossary.
- **What actually happened?** Words in the transcript, actions on the desktop and records in the systems can disagree. The transcript can be wrong (ASR), attribute words to the wrong speaker (diarization) or have holes (recording gaps).
- **Which rules governed that moment?** The glossary, script, policy and disclosure **in force on the interaction date** — not today's.
- **Was the customer harmed, and what restores them?** Refunds, reversals, restored rewards, logged complaints, SCRA referrals, honored cancellations — sometimes only after asking the customer what they want.
- **Is a colleague at fault?** Or did they follow a stale script, a supervisor's cheat sheet or a desktop that never showed the opt-out?
- **Who else is affected?** One complaint can reveal 41 customers read the same wrong script, or one colleague's 15 enrollments without consent.

### Why it matters
- **Enforcement history.** US card issuers have paid well over a billion dollars in refunds and penalties for add-on products sold or billed deceptively (Capital One 2012, Discover 2012, Chase 2013, Bank of America 2014, Citibank 2015), and for accounts opened without consent under sales pressure (Wells Fargo 2016, US Bank 2022, Bank of America 2023). *(research §3)*
- **Coverage.** Human QA samples a small fraction of interactions; misconduct is rare (~3.6% in the reference program), so sampling misses most of it and the labels that exist are noisy and biased toward what a scanner happened to flag.
- **Fairness in both directions.** False findings harm colleagues; missed findings harm customers; systemic causes blamed on individuals never get fixed.

### Why it's hard
1. **The evidence is split across modalities.** Misconduct can be purely conversational (pressure), purely structural (a sale on a prohibited outbound call) or only visible by joining a transcript, a desktop event and a disclosure (the fee said vs the offer submitted).
2. **Transcripts are claims about audio.** ASR substitutions flip consent words; diarization moves sentences between speakers; Spanish calls go through an English model.
3. **Rules change and sometimes reverse.** Scripts lag policy; glossaries tighten on a date; a federal fee rule was vacated a year after it was finalized.
4. **Harm, fault and cause come apart.** The same interaction can require a refund, no colleague finding and a script fix.
5. **Patterns live across interactions** — a colleague's cancellations, a team's shared phrase, an incident window — and are easy to over-apply to innocent neighbors.
6. **The monitored content is adversarial.** Colleagues know they are monitored; transcripts and notes can contain instructions aimed at the monitor.
7. **No human downstream.** Every finding must be evidence-verified, calibrated, challenged when high-impact and fail safe when uncertain.

### Why an agent beats a keyword scanner or a single prompt here

| | Keyword / rules scanner | Single-prompt LLM | Agent system |
|---|---|---|---|
| Deciding which rule applies | Hard-coded phrases, one glossary version | Plausible, undated general knowledge | Retrieves glossary, script, policy and disclosure *as of the interaction date*; re-plans when root cause shifts |
| Finding facts | Only the transcript fields it was coded for | Only what is pasted in | Plans, queries systems of record, walks prior interactions, requests re-transcription and colleague statements, waits for them |
| Transcript quality | Treats ASR text as truth | Treats ASR text as truth | Uses word and speaker confidence, channel metadata, recording gaps; obtains better evidence before deciding |
| Contradictions | None | Accepts the dominant narrative | Evidence matrix of said vs did vs recorded; competing hypotheses |
| Cross-interaction patterns | Threshold rules that over-fire on teams | No memory | Graph traversal, sandbox statistics, fan-out review per interaction, bounded pattern findings |
| Arithmetic and time | Only pre-coded | Unreliable (fees, wpm, time zones, business days) | Sandbox computation with recorded inputs |
| Attribution | Always the colleague | Usually the colleague | Colleague vs script vs system vs supervisor material, each with evidence |
| Stale beliefs | Silent rule drift | N/A | Governed memory: supersede, retract, consolidate, purge |
| Knowing when to stop, wait or challenge itself | Runs everything or nothing | Never doubts itself | Early stops, suspend/resume on external events, automated review panel with computed confidence and conservative defaults |

Section 3 of the case catalog lists how each alternative fails, case by case.

---

## 2. Domain background

### Who's involved
Customer · front-line colleague · supervisor and team · the contact-center platform (telephony, recorder, ASR, chat) · the colleague desktop (CRM, offer and order systems) · card platform (accounts, ledgers, rewards) · credit bureaus · complaints function · conduct risk monitoring (the function this system automates) · product, policy and script owners · regulators (CFPB, OCC).

### The monitoring lifecycle
Interaction → recording + ASR (routed by language) → redaction → **selection** (scanner flags, risk ranking, complaints, lookbacks, protected random slice) → **review** (evidence gathering, as-of rules, findings) → **governance** (verifier, panel when required, computed confidence, conservative default) → **outcomes** (customer remediation, colleague coaching/finding, control records) → feedback (complaints, cancellations, precedents, memory).

### The misconduct taxonomy
Eleven categories in the invented `CLB-GLOSS` glossary: pressure after decline (MC-01), enrollment without affirmative consent (MC-02), misrepresentation of terms (MC-03), omitted or unclear disclosure (MC-04), inaccurate credit-reporting information (MC-05), leveraging servicing or blocking cancellation (MC-06), sale in a prohibited context (MC-07), undisclosed product switching (MC-08), sale to a protected situation (MC-09), misinformation about or obstruction of rights (MC-10), inaccurate records (MC-11). Details: catalog §1.2.

### Regulation (summary; research §2)
UDAAP is the charging theory in card conduct cases. Reg Z governs ability-to-pay for line increases, over-limit opt-in, change-in-terms notice and billing-error handling; FCRA governs credit inquiries and prescreened offers; ECOA/Reg B prohibits using age, national origin and other bases; SCRA caps pre-service card interest at 6%; TCPA/TSR shape outbound calling and consent; the CFPB's LEP statement shapes language access; FinCEN's elder-exploitation advisory lists behavioral red flags. Copperlake's SOPs operationalize these — they are invented, and they are what the agent enforces.

### Where the complexity really comes from
Not from the number of rules but from how **evidence quality, time, attribution and populations** interact: a word the ASR got wrong, a script that lagged a policy, a clock that was nine seconds fast, a preference that never synced, a phrase that spread through a team chat.

---

## 3. Example reviews

### C06 — Silent Switch (why desktop events, adversarial review and waiting exist)
A customer asks to get rid of a $95 annual fee: "whatever you need to do." The colleague says "I've taken care of that." The desktop shows a product change that forfeited 48,200 miles and trip protection for a December trip; the transcript never mentions it; the colleague's CRM note claims it was disclosed. The agent re-routes from a fee question to a product-change review, rules out a recording gap, requests a colleague statement and waits for it, runs a customer-advocate vs colleague-advocate panel, substantiates undisclosed switching and an inaccurate record, then asks the customer whether to restore the product — and waits for the answer.

### C04 — The Stale Script (why as-of retrieval, attribution and memory supersession exist)
A customer's score dropped after a colleague promised a line increase "will not impact your credit score." The colleague read the approved script word for word — but the credit-line policy changed on 1 October and the script was never updated. The agent retrieves both documents as of the call date, attributes the finding to the script, supersedes a memory note that was true under the old policy, and finds 41 customers who heard the same sentence before a hard inquiry.

### C11 / C11b — One Colleague's Pattern / Same Team, Clean Record (why graph memory, fan-out and fairness checks exist)
One complaint leads to one colleague's 23 add-on enrollments and a 61% early-cancellation rate. The agent fans out one subagent per enrollment call, substantiates 15, clears 6, marks 2 as insufficient evidence with customer-protective remediation, and writes an evidence-backed pattern to the graph. The next day a teammate with even higher sales is flagged by a team-level scanner rule — and cleared, with a logged decision not to write anything about them.

### C14 — Asked Three Times (why the conservative default exists)
A customer who doesn't know who they are talking to, thinks the call is about the electric bill and says "whatever you think is best, dear" three times is upgraded to a $450 card. Age is on file and must not be used; a memory note that uses it is purged. The panel can't reach 0.75 on a vulnerability judgment, so the customer is restored and the colleague receives coaching, not a finding.

---

## 4. The data ecosystem

### Inventory (generated Stage 1 dataset)

| Kind | Content | Volume |
|---|---|---|
| Structured | customers, accounts, flags, preferences, colleagues, teams, interactions, callback requests, offers, enrollments, product changes, credit-line requests, bureau inquiries, installment plans, fee/rewards ledgers, statements, payments, complaints, coaching records, legacy QA reviews, scanner rules/flags, incidents, config changes | 1,173 customers/accounts, 64 colleagues, 6,527 interactions (6,500 non-hero), 1,041 legacy QA reviews |
| Events | desktop events (screen substitute), interaction events (hold, overtalk, gaps), account events | 41,873 |
| Transcripts | turn-level JSON with word timings, ASR and speaker confidence, channel metadata | 6,527 files; 32,032 turns; 169,479 timed words |
| Documents | CRM notes, internal comms, complaint narratives | 6,369 |
| Corpus | regulation excerpts, SOPs, glossary v6/v7/v8, scripts, product disclosures, incentive plan, skills | 53 versioned documents + 11 skills; 273 SQLite chunks |
| Precedents | adjudicated prior findings | ~40 |
| Memory seed | agent memory notes (valid, stale, over-generalized, raw, duplicate, prohibited), two legacy run traces | 58 notes + 2 traces |
| On-request | re-transcriptions, audio recovery results, colleague statements | 4 artifacts |
| Simulation | customer personas for outreach replies | 4 personas |
| Graph | projection of the above | 10,023 nodes, 27,259 edges |
| Ground truth | 23 hero case files, background gold labels, reviewer baseline, Q01 sweep, capability coverage | evaluator only |

Field-level detail: [`docs/design/03-data-dictionary.md`](docs/design/03-data-dictionary.md).

### Hero vs background
Hero records (ID range `9xxxx`) are hand-built per case and planted inside a realistic background. Background interactions have gold labels at **3.6% misconduct prevalence** plus ~1% control gaps, and ~16% carry legacy human QA verdicts from three reviewers whose noise reproduces the reference program's human baseline. Agents never see `is_hero`, ground truth or simulation files.

### The simulated clock
`AS_OF` = **Monday 2026-11-16 09:00 America/Chicago**. Records carry `available_at`; on-request artifacts are released after their delay; customer replies and colleague statements arrive on the virtual clock. The monitoring SLA (10 business days, US bank holidays excluded) sets every review's latest safe decision time.

---

## 5. Relationships and review paths

### The spine
```
Customer ─HOLDS→ Account
   │                 │
   └─PARTICIPATED→ Interaction ←PARTICIPATED─ Colleague ─MEMBER_OF→ Team ←SUPERVISES─ Supervisor
                    │   │   │                                      │
      NEXT_CONTACT ─┘   │   └─ transcript turns / desktop events   └─ AUTHORED → InternalMessage
                        │
   Offer / Enrollment / ProductChange / Plan ─(…_IN)→ Interaction ←COMPLAINS_ABOUT─ Complaint
   CallbackRequest ─CREATED_IN/FULFILLED_BY→ Interaction ←AFFECTED─ Incident / ConfigChange
   Interaction ─GOVERNED_BY{as_of}→ Document@version ←DECIDED─ Precedent
```

### Paths the cases require (discoverable, not handed over)
- **Callback chain:** outbound call → callback request → originating chat → stated purpose (C02, C02b).
- **Prior protected situation:** call → customer → earlier chat → hardship enrollment / opt-out → desktop banner or its absence (C08, C15).
- **Colleague lookback:** complaint → interaction → colleague → all enrollments → cancellations/complaints → per-interaction review (C11), with a scope boundary at the colleague (C11b).
- **Shared material:** interaction → phrase → semantically similar segments → colleagues → team → supervisor → internal message (C12).
- **Population from a control failure:** interaction → governing script/policy/config version → all interactions in its window matching a condition (C04, C10, C15, C18).
- **Said vs did:** transcript turn → aligned desktop event / order record / ledger row (C05, C06, C07b, C16, C20).

### What's searchable vs traversable vs computed

| Searchable (semantic/FTS) | Traversable (graph) | Computed (sandbox) |
|---|---|---|
| glossary, scripts, policies, disclosures by meaning and date | callback chains, contact sequences, colleague → team → supervisor, incident windows | fee amounts, wpm, time-zone and clock-offset alignment, business-day SLAs |
| transcript segments by paraphrase (speaker-filtered) | colleague → enrollments → cancellations → complaints | cancellation-rate statistics vs program baseline |
| precedents, complaints, CRM notes, internal comms | material → usage (agent-written) | affected populations, refunds, Q01 risk scores |

---

## 6. Memory design

### Chosen stack (POC, local, no servers) — same as CatcherAI
| Store | Technology | Why |
|---|---|---|
| Persistent / structured | **SQLite** (`conduct.sqlite`; FTS5 over transcripts and documents) | zero setup; exact joins; transactional review state |
| Semantic / vector | **sqlite-vec** in the same file (corpus chunks, transcript segments with speaker and date metadata, precedents, notes, memory) | similarity *and* metadata filters (`as_of`, speaker, channel, status) |
| Graph | **LadybugDB** (embedded Cypher) loaded from `graph/*.jsonl`, **NetworkX** fallback behind the same interface | multi-hop traversal without a server |

### What goes where, and why

| Information | Store | Requirement that justifies it |
|---|---|---|
| Interactions, offers, enrollments, ledgers, flags, preferences, incidents, review state | **Persistent** | exact timestamps, sums and joins; auditable system of record |
| Desktop and interaction events | **Persistent** (append-only) | ordering and alignment |
| Transcript turns and words | **Persistent** (raw JSON) + **semantic** (segment embeddings with speaker/channel/date) | exact quotes and timings for evidence; paraphrase search for spread (C12) |
| Glossary, scripts, policies, disclosures, regulation | **Semantic** with version metadata | plain-language questions; date decides the answer |
| Precedents | **Semantic** + graph edge to decided interactions | find look-alikes, then distinguish |
| Customer ↔ interaction ↔ colleague ↔ team ↔ material ↔ incident | **Graph** | callback chains, lookbacks, shared material, incident windows |
| Agent long-term notes | **Persistent** lifecycle table + **semantic** index | retrieval by meaning; exact lifecycle state |

### Other memory kinds

| Kind | Warranted? | Implementation |
|---|---|---|
| **Working memory** (per review) | Yes | review file: claims with turn IDs, evidence matrix, hypotheses, open questions, deadlines, plan, budget |
| **Shared blackboard** for subagents | Yes, scoped | fan-out reviewers (C11, C12) and panel roles write findings with source IDs; the orchestrator resolves |
| **Episodic** (run traces) | Yes | every run writes one; legacy traces show pre-automation human steps |
| **Procedural** (skills) | Yes | review playbooks per product/program, loaded by route |
| **Semantic long-term notes** | Yes, governed | memory-governance SOP lifecycle |
| **Colleague-scoped notes** | Yes, **bounded** | evidence-backed, time-bounded, scoped to one colleague, never imported to teammates, never containing demographic or character judgments |
| **Customer risk profiles** | **No** | turns into labels and bias; facts with sources only |

### Consolidation and forgetting, concretely

| Operation | Trigger in the data | Expected action |
|---|---|---|
| **Supersede** | MEM-0310 (CLI always soft) vs CLI v6 (C04); MEM-0320 ($8 late-fee cap) vs vacatur (C07); MEM-0350 vs glossary v7 (C19) | mark superseded with `valid_to`, pointer to source |
| **Retract** | a background note derived from a precedent later marked wrong | retract with correction note |
| **Consolidate** | MEM-0341–0343 + C11 findings → one colleague pattern note; five T-SAT-2 observations → one material note (C12); MEM-0351–0356 re-consolidated under v7 (C19) | one validity-bounded note with sources; archive raw notes |
| **Purge** | MEM-0396 age-based upgrade rule (C14) | purge content, keep tombstone |
| **Skip (deliberate non-write)** | C01, C03, C10, C11b | `memory_write_skipped` with reason |
| **Expire / dedupe** | tool-timeout noise and duplicate notes in the seed | TTL removal; archive duplicate |
| **Graph write** | colleague pattern (C11); material usage (C12) | hypothesis nodes/edges with evidence and `status=active`; bounded actions only |

---

## 7. The evidence ecosystem

### What the agent can discover, compare, validate and weigh

| Evidence | Holder | Discover via | Validate how | Weight depends on |
|---|---|---|---|---|
| ASR transcript | recorder/ASR | `get_transcript` | word & speaker confidence, channel metadata, gaps | ASR model fit, confidence at the decisive span |
| Re-transcription / audio recovery | QA vendor (simulated) | `request_retranscription`, `request_audio_recovery` (delayed) | treated as higher fidelity | availability before the SLA |
| Chat / secure message | platform | `get_transcript` | exact text | — |
| Desktop events | colleague desktop | `get_desktop_events` | clock offset per workstation | alignment with speech |
| Offers, enrollments, product changes, plans | order systems | SQL tools | timestamps vs call window | source system clock |
| Ledgers (fees, rewards, payments), statements | card platform | SQL tools | sums, dates | posting vs event date |
| Flags, preferences, sync status | CRM | SQL tools | set vs synced timestamps | whether the colleague could see it |
| Callback requests, prior contacts | CRM / graph | graph queries | purpose, window, consent | same-product exception |
| CRM notes, colleague statements | colleague | tools | **untrusted assertions**; must be corroborated | contradiction with transcript |
| Complaints | customer / regulator portal | SQL, semantic | received vs visible date | trigger and remediation dates |
| Internal comms | team chat | semantic search | author, date, audience | approval status |
| Incidents, config changes | IT | SQL | time windows | overlap with the interaction |
| Customer replies | customer (simulated) | `send_customer_outreach` (delayed) | persona | what they want now |
| Glossary, scripts, policies, disclosures | Copperlake / regulators | semantic retrieval with `as_of` | effective dates, status | precedence (§8) |
| Precedents, memory | prior reviews | retrieval | verification against current sources | never evidence by themselves |

### Typically available vs typically missing
Available: exact chat text, desktop events, ledgers, offers. Often degraded: ASR text on noisy or non-English calls, speaker attribution in overlap. Sometimes missing: recording segments, synced preferences, a colleague's actual intent. Arrives late: bureau inquiries, re-transcriptions, customer replies, regulator-portal complaints.

### Conflicts are first-class
Said vs submitted (C05), said vs did (C06, C16), note vs transcript (C06, C13, C20), ASR vs re-transcription (C01, C10), speaker label vs channel (C12), memory vs current rule (C04, C07, C19), pattern vs individual evidence (C11, C11b), script vs policy (C04). Every conflict becomes a `contradiction_detected` event with both sources and a resolution.

---

## 8. The policy ecosystem and automated governance

### Layers and precedence
1. **Regulation** (UDAAP, Reg Z, FCRA, ECOA/Reg B, SCRA, TSR) — the floor for customer treatment.
2. **Copperlake policies and SOPs** — how the bank operationalizes 1; cannot lower it.
3. **Misconduct glossary** — the classification standard for colleague conduct at a point in time.
4. **Colleague handling cards (scripts)** — what colleagues were told to say; if a script contradicts a policy, the script is a control gap, not a colleague defense against the customer outcome.
5. **Product disclosures and fact sheets** — the truth about terms.
6. **Incentive plan** — context for risk, never evidence of individual misconduct.
7. **Precedents and memory** — persuasive context only.

### Corpus (to be authored; `data/corpus/`)

| Doc ID | Versions | Content |
|---|---|---|
| `REG-UDAAP` | — | CFPA §1031/1036 abridged |
| `REGZ-1026.51`, `REGZ-1026.9`, `REGZ-1026.13`, `REGZ-1026.56` | — | abridged |
| `REGZ-1026.52` | `@pre-2024`, `@2024-03-15` (status `vacated`, effective_to 2025-04-15) | late-fee safe harbor (C07) |
| `FCRA-INQUIRY`, `FCRA-PRESCREEN` | — | permissible purpose; firm offers (paraphrase) |
| `REGB-1002` | — | prohibited bases, adverse action (abridged) |
| `SCRA-3937` | — | 6% cap (abridged) |
| `TSR-310` | — | material terms before consent (abridged) |
| `CLB-SOP-SAL-001` sales practices & consent | v3, **v4** | affirmative consent, disclosure clarity (≤ 220 wpm), price before consent |
| `CLB-SOP-SAL-002` outbound contact | **v3** | outbound-sale prohibition and callback exception |
| `CLB-SOP-SRV-002` fee waivers | **v2** | one courtesy waiver per 12 months, never conditional |
| `CLB-SOP-SRV-003` complaints | **v5** | complaint definition, logging, acknowledgment |
| `CLB-SOP-SRV-004` remediation matrix | **v2** | what restores the customer per finding type |
| `CLB-SOP-VUL-001` vulnerable customers & hardship | **v2** | indicator list; no credit sales in active hardship |
| `CLB-SOP-SCRA-001` | **v3** | referral duty on any mention of orders/active duty |
| `CLB-POL-CLI` credit line increases | v5, **v6** (2026-10-01) | soft vs hard inquiry rules; ability to pay |
| `CLB-GLOSS` misconduct glossary | v6, **v7** (2026-07-01), v8 (2026-11-01) | categories, red-flag patterns, exceptions |
| `CLB-CHC-BT`, `-CLI`, `-PC`, `-ADDON-CS`, `-ADDON-CW`, `-FLEX` (EN/ES), `-RET` | per catalog §0.1 | scripts |
| `CLB-PRD-*` | per product | fact sheets, BT offer disclosures, CardShield/CreditWatch/Flex terms, card benefits |
| `CLB-INC-2026-Q4` | — | incentive plan |
| `CLB-SOP-CRM-001` monitoring program | v4, **v5** (2026-09-01) | selection, random slice, 10-business-day SLA |
| `CLB-SOP-CRM-003` automated conduct adjudication | v3, **v4** (2026-10-01) | panel, thresholds, defaults, allowed actions |
| `CLB-SOP-CRM-004` fairness in monitoring | **v2** | prohibited features for customers and colleagues |
| `CLB-SOP-CRM-005` memory governance | **v2** | note lifecycle, colleague-scoped note limits |

Every document carries front matter: `doc_id, version, effective_from, effective_to, status (active | superseded | scheduled | vacated), supersedes, provenance (regulation_abridged | paraphrase | invented)`.

### Automated governance (`CLB-SOP-CRM-003@v4`) — replaces human testers

**Panel required** when either (A) a proposed finding is severity **high** *and* at least one of: customer remediation > $250; vulnerability or hardship involved; rights misinformation; colleague-level pattern; systemic population ≥ 10 customers — or (B) the computed confidence of any proposed adverse finding falls in [0.60, 0.85). A severity-high finding with none of the (A) conditions and computed confidence ≥ 0.85 is decided without a panel (C05, C07, C16, C20).

**Panel:** a **customer advocate** and a **colleague advocate** work independently from the same review file; an independent **adjudicator** decides; **verifier checks** gate the result (evidence quotes verified by turn ID and substring, policy citations verified by `doc_id@version` and as-of date, arithmetic reproduced in the sandbox, prohibited features absent, allowed actions only).

**Computed confidence** combines verifier pass rate, citation verification, evidence coverage of the decisive facts, transcript-quality at decisive spans and panel agreement. A model's self-reported confidence is recorded but never used for gating *(research §6.2)*.

**Thresholds and defaults:**

| Decision | Threshold | Below threshold (conservative default) |
|---|---|---|
| Adverse colleague finding | computed confidence ≥ **0.75** | `no_adverse_finding`; coaching and enhanced monitoring allowed |
| Customer remediation | harm plausible (≥ 0.50) **or** consent unverifiable | remediate in the customer's favor when reversal leaves the customer no worse off; otherwise offer and wait for the customer's choice |
| Systemic control record | population computed in sandbox with a recorded query | record observation only |

**Allowed automated actions:** `refund_fee`, `refund_premiums`, `reverse_enrollment`, `reverse_flex_plan`, `reverse_upgrade`, `reverse_product_change` (after customer confirmation), `restore_rewards`, `waive_annual_fee`, `honor_cancellation_request` (explicit recorded request + confirmation), `log_complaint`, `open_scra_review`, `correction_letter`, `suppress_solicitation`, `send_customer_outreach`, `request_colleague_statement`, `record_colleague_finding`, `assign_coaching`, `enhanced_monitoring`, `targeted_lookback`, `control_gap_record`, `script_update_request`, `scanner_rule_update_request`, `quarantine_unapproved_material`, `systemic_remediation_record`, `graph_write`, memory lifecycle operations.

**Forbidden:** any employment, disciplinary or compensation action (termination, suspension, incentive clawback); closing or restricting customer accounts on the bank's initiative; bureau deletion requests for authorized inquiries; contacting regulators; contacting anyone other than the customer about the customer; any action or text that relies on a prohibited basis.

---

## 9. How the dataset is generated

### Principles (inherited from CatcherAI)
- **Entity- and event-sequence-based with explicit relationship seeding** — patterns are planted (colleague pattern, shared material, incident windows), not hoped for.
- **Hero cases are code:** each builder creates customers, interactions, transcripts, desktop events, ledger rows, documents, on-request artifacts, personas and ground truth together.
- **Deterministic:** fixed seed; identical output every run; stdlib Python.
- **Validated:** `validate.py` checks schemas, joins, `available_at` consistency, arithmetic in ground truth, capability coverage (every capability primary in ≥ 3 cases) and **discoverability** — e.g. that a SQL query finds exactly 41 affected CLI calls (C04), that speaker-filtered semantic search over T-SAT-2 transcripts returns the 17 planted segments in its top 25 (C12), that COL-4421's early-cancellation rate is the program's highest (C11) and that COL-4425's is not anomalous (C11b).

### Transcript generation
- **Background:** a template grammar per interaction intent (greeting, authentication, need, offer, consent, close) with colleague style variation, customer persona variation and deterministic misconduct insertions for gold positives; then an **ASR noise model** (substitutions from a confusion list weighted toward consent- and fee-critical words, deletions, insertions), **diarization noise** (~2% of phone turns misattributed in overlap, with channel metadata kept correct), word timings from speaking-rate distributions, and Spanish/code-switched segments on the bilingual queue.
- **Heroes:** hand-written turn by turn; the ASR and re-transcription versions are both authored so the difference is exact.

### Background distributions (deterministic Stage 1 settings — POC assumptions, not production-calibrated)

| Dimension | Setting |
|---|---|
| Channels | phone 68% · chat 24% · secure message 8% |
| Direction (phone) | inbound 91% · outbound 9% (of which 40% callbacks) |
| Intents | balance/payment 22% · fees 14% · lost/replacement card 11% · rewards 8% · product questions 8% · CLI 7% · BT 6% · close/retention 5% · hardship 4% · disputes 4% · address/profile 6% · other 5% |
| Sales/enrollment opportunity | ~28% of interactions |
| Bilingual queue | 9% of phone interactions; 55% Spanish or mixed |
| ASR mean confidence | en ~0.86 ± 0.06; es on es model ~0.83; es on en model ~0.50 |
| Gold misconduct prevalence | 3.6% of interactions; bright-line 60% / judgment 40% |
| Category mix (of positives) | MC-02 24% · MC-03 18% · MC-04 16% · MC-06 10% · MC-05 8% · MC-01 7% · MC-10 6% · MC-09 4% · MC-11 4% · MC-07 2% · MC-08 1% |
| Legacy QA coverage | 16%, selected 70% by scanner flags / 20% complaints / 10% random |
| Reviewer noise | calibrated to R-A 79/76, R-B 74/71, R-C 75/77 precision/recall vs gold |
| Scanner | 14 rules; ~9% of interactions flagged |
| Early add-on cancellation | program baseline 11% within 30 days |

### Planted structures

| Structure | Seeding |
|---|---|
| Stale CLI script population | 41 hard-inquiry calls after the script sentence + 6 correct-warning controls (C04) |
| Colleague consent pattern | COL-4421: 23 enrollments, 15 non-consensual, 6 clean, 2 gap-affected (C11); COL-4425 high-volume clean control (C11b) |
| Shared material | ICM-9001501 → 17 similar segments across 5 colleagues, 2 non-misrepresentations incl. a diarization swap (C12) |
| ASR routing window | CHG-2026-1019-ASR → 63 bilingual calls on the English model (C10) |
| Preference-sync incident | INC-9001801 → 1,214 delayed opt-outs, 9 solicited (C15) |
| Recorder failover | INC-9002101 → 23 calls with gaps, 4 with sales in the gap (C18) |
| Post-call enrollments | COL-3122: 6 further CreditWatch enrollments within 5 minutes after call end (C16) |
| Policy changes | CLI v6, CHC-BT v5, glossary v7/v8, CRM-001 v5, CRM-003 v4, vacated late-fee rule |

### Controlling difficulty

| Knob | Easier | Harder |
|---|---|---|
| Transcript quality | higher ASR confidence, no swaps | more substitutions on consent words; more diarization swaps |
| Evidence timing | artifacts available before `AS_OF` | re-transcriptions after the SLA; some never arrive |
| Narrative honesty | colleague statements concede | statements restate notes; customers misremember |
| Policy proximity | `AS_OF` far from effective dates | interactions straddle changes |
| Pattern signal | strong cancellation outliers | outliers near program baseline; more clean calls per pattern colleague |
| Label noise | reviewers match gold | reviewer disagreement on judgment categories rises |
| Memory hygiene | no stale notes | stale notes with high access counts |

### Scaling
Parameterized scenario families per hero (e.g. 50 "stale script" variants with different policy/script gaps and populations), more sites and languages, audio-derived features, additional products (cash advance, authorized users, autopay), collections servicing under Reg F.

---

## 10. Architecture component → the scenario that forces it

Machine-checkable version: `data/generated/ground_truth/capability_coverage.json` (to be generated). Each row names the cases that break if the component is removed.

| Component | Forcing scenario(s) | What breaks without it |
|---|---|---|
| **Agents** | C06, C11, C12, C14 | Fixed scripts can't decide to re-route a fee call into a product-change review, expand one complaint into a lookback, or chase a phrase to its source |
| **Router** | C02 (callback exception), C03 (L1 stop), C10 (language), C13 (servicing track), C15 (solicitation after opt-out), Q01 (portfolio) | Every interaction gets the same heavy flow; Spanish calls get English rules; clean calls burn budget |
| **Loop engineering** with termination | C03 stops early; C01, C06, C17, C18 wait and resume or decide at the latest safe time | Over-review of true statements; decisions made before better evidence arrives; SLA misses |
| **Agent graph** (plan → gather → verify → adjudicate → act, back-edges) | C04 (root cause shifts to script), C06 (re-route + panel), C11 (lookback), C12 (material), C14 (default) | Linear chains commit to the first hypothesis — usually "blame the colleague" |
| **Subagents** | C11 (per enrollment), C12 (per phrase hit), C06/C14 (advocates + adjudicator), Q01 (per candidate) | One context can't hold 23 transcripts; no independent perspectives for adversarial review |
| **Tool / function calling** | C01 (re-transcription), C05 (offer submission), C16 (enrollment record), C20 (word timings); every case | Systems of record and evidence requests are only reachable through tools |
| **Harness** | C01/C10 (delayed re-transcription), C06 (colleague statement + customer reply), C15/C17/C18 (customer replies, audio recovery), Q01 (weekly population); all (budgets, traces) | Nothing arrives late, nobody replies, runs can't suspend and resume |
| **Skills** | C05 (balance transfers), C08 (hardship), C09 (SCRA), C13 (complaints), C17 (retention) | One giant prompt mixing every product's rules; program-specific duties get skipped |
| **Persistent memory** | C02 (callback), C05 (offer submitted), C07b (event times), C15 (sync status), C16 (enrollment time), Q01 | Exact timestamps, amounts and statuses can't come from text retrieval |
| **Graph memory** | C02/C02b (callback chain), C08 (prior chat), C11/C11b (colleague scope), C12 (team → supervisor → material) | Evidence in other interactions stays invisible; lookbacks leak to teammates |
| **Semantic / vector memory** | C04 (script sentence population), C09 (SCRA text), C12 (paraphrases), C17 (precedents), C19 (glossary conditions) | Keyword search misses paraphrase; look-alike precedents aren't found to be distinguished |
| **Working memory / blackboard** | C06 (hypotheses), C11 (23 results), C12 (17 hits), Q01 | Facts and open questions scroll out of context |
| **Sandbox / REPL** | C04, C05, C07b, C10, C11, C16, C18, C20, Q01 | Fees, wpm, clock offsets, time zones, business days and statistics done in prose → wrong findings |
| **Agent read paths** | C04, C07, C10, C11b, C14, C19 | Stale, out-of-scope or prohibited memory decides the case |
| **Agent write paths** | C03/C11b (skip), C04/C07/C19 (supersede), C11/C12 (consolidate + graph write), C14 (purge); outcomes and actions everywhere | Lessons don't persist, wrong beliefs persist, or teammates inherit a colleague's pattern |
| **Automated governance** | C04, C06, C08, C09, C11, C12, C14, C18 (panel); C05, C16, C20 (verifier-gated without panel) | Unsupervised findings either overreach (employment actions, age-based reasoning, guilt by team) or can't decide judgment calls at all |
| **Evaluation** | every case's checks; background gold vs legacy reviewers; Q01; pass^k | No way to tell a lucky demo from a reliable monitor |

### Evaluation design
- **Deterministic checks** on the assessment record: finding categories and statuses, attribution, customer remediation actions and amounts, colleague outcome, control records and populations, panel use and conservative defaults, memory operations.
- **Process checks:** required key facts found (by source ID), contradictions surfaced, `must_not` absent, required versions cited, evidence spans verified.
- **Detection quality on the background:** interaction-level precision, recall and FP rate vs gold, **side by side with the three legacy reviewers and the scanner** (the reference program's comparison, reproduced); per-category and bright-line vs judgment breakdowns; colleague-level recall; PR curves.
- **Reliability:** pass^k over repeated runs.
- **Calibration:** computed confidence vs empirical correctness (ECE/Brier) — to tune 0.75 on evidence.
- **Fairness:** matched pairs (language, ASR quality, site) with identical conduct must receive identical findings; no prohibited features in any payload.
- **Robustness:** injection cases never change outcomes.
- **Efficiency:** tool calls vs budget; early termination on L1; cost per interaction.
- **Trajectory completeness:** every model/tool/store/sandbox access has an event; every assessment field has provenance.

---

## 11. Agent behavior this data enables

- **Changing course mid-review** — C04 (colleague → script), C06 (fee → product change), C12 (individual → material), C15 (colleague → system).
- **Detecting contradictions** — said vs submitted (C05), said vs did (C06, C16), note vs transcript (C06, C13, C20), ASR vs re-transcription (C01, C10), speaker label vs channel (C12), memory vs rule (C04, C07, C19).
- **Deciding further digging isn't worth it** — C03 (true statement), C13 (portal complaint can't change the finding).
- **Getting better evidence instead of guessing** — C01, C10 (re-transcription), C18 (audio recovery), C06 (colleague statement).
- **Asking the customer what they want** — C06 (restore?), C15 (keep the transfer), C17 (confirm closure before the refund window).
- **Challenging its own findings** — panels on C04, C06, C08, C09, C11, C12, C14, C18; conservative default when confidence stays below 0.75.
- **Separating harm, fault and cause** — C04, C12, C14, C15, C18.
- **Reasoning about which rule version governs** — C04, C05, C07, C10, C19.
- **Temporal reasoning** — business-day SLAs with holidays, time zones without DST, workstation clock skew, effective dates, `available_at`.
- **Distinguishing precedents** — PRE-0017 vs PRE-0044 (C17), PRE-0022 (C05), PRE-0031 flawed (C09).
- **Fairness under suspicion** — C10 (language), C11b (team), C14 (age), Q01 (prohibited features).
- **Robustness to the monitored** — C20.
- **Governing its own memory** — every lifecycle operation appears at least once.

Where behavior **emerges** rather than being scripted: the order of evidence gathering, which hypothesis is tested first, how fan-out results are aggregated, how panel arguments are phrased. Ground truth constrains outcomes and required findings, not the path.

---

## 12. Why this is a compelling demonstration

### For a financial-services and conduct-risk audience
- It is built on the **real enforcement record** — add-on mis-selling, unconsented enrollment, incentive-driven misconduct — and real rule reversals, not generic "bad words".
- It reproduces the **reference program's human-vs-AI comparison** on data where the gold truth is known, including noisy reviewers and biased sampling.
- It gets **attribution** right: remediation for customers even when colleagues are cleared; systemic fixes when the script or the system failed; no guilt by team.
- It replaces two levels of human testers with an **auditable automated review panel**: every position, the computed confidence, the flip fact and the conservative default are on the record.
- It treats **fairness, vulnerable customers and memory governance** as controls in code.

### For an AI-engineering audience
- Every component is **load-bearing**, with named cases that fail without it.
- It exercises the hard parts: **evidence quality as a variable, cross-modal joins, versioned retrieval, late evidence, suspend/resume, fan-out over populations, adversarial self-review, computed rather than self-reported confidence, injection-resistant review of adversarial content, and memory that is wrong, stale or prohibited**.
- It is **evaluable** end to end: deterministic checks, trajectory-derived capability checks, pass^k, calibration, fairness pairs and a baseline comparison.
- Insights that make the audience lean forward: *the approved script can be the misconduct*; *a transcript is a claim about audio*; *benefit of the doubt runs both ways*; *a pattern is a lead, not evidence*; *the most careful monitor is the one being talked to*.

---

## 13. From POC to production

| Area | POC | Production |
|---|---|---|
| Data | synthetic, ~6,500 interactions | recorder/ASR, CCaaS, CRM, desktop analytics, card platform, complaints and HR-system integrations; streaming; PII vaulting |
| Audio | text transcripts + delayed re-transcription | audio access for targeted re-listening, stereo channels, prosody features, speaker verification |
| Stores | SQLite + sqlite-vec + LadybugDB | Postgres (+ pgvector) with row-level security, graph service, object storage; retention per records policy |
| Rules | invented Copperlake SOPs, abridged regulation | legal- and compliance-owned rule library with effective-date releases, regression suites and backtests on every change |
| Governance | automated panel, verifier, thresholds | same, plus model-risk validation (SR 11-7), challenger models, drift and calibration monitoring, kill switches, employee due-process integration (appeals) |
| Colleague outcomes | coaching and finding records | integration with HR and employee-relations processes, which remain human decisions outside the system |
| Evaluation | 23 hero cases + synthetic gold | calibrated against historical adjudications and targeted re-reviews; continuous random-slice measurement of prevalence and recall |
| Security | injection cases, redaction | red-teaming, least-privilege tools, secrets management, PCI scope reduction at capture |
| Fairness | prohibited features, matched pairs | disparate-impact monitoring for customers and colleagues, documented remediation |
| Vendor landscape | — | integrate or compete with NICE, Verint, CallMiner, Observe.AI, Level AI, AWS Contact Lens; build vs buy per layer |

---

## 14. Target repository layout

Mirrors CatcherAI so patterns, tests and tooling transfer. Nothing under `src/`, `config/`, `skills/`, `data/`, `tests/` or `frontend/` exists yet.

```
ConductAI/
├── README.md · handoff.md · pyproject.toml · uv.lock · dev.sh
├── docs/
│   ├── reference/          reference program brief
│   ├── research/           01 domain research + briefs/
│   ├── design/             02 case catalog · 03 data dictionary · 04 architecture research · 05 architecture · 06 eval results · 07 console
│   └── prompts/            01 data foundation · 02 implementation · 03 console kickoff
├── data/
│   ├── corpus/             regulation · policies · glossary · scripts · products · incentives · skills · author_corpus.py
│   ├── generator/          gen.py · world.py · heroes/ · background.py · transcripts.py · asr_noise.py · derived.py · capabilities.py · memory_seed.py · precedents.py · validate.py · load_sqlite.py
│   └── generated/          (see data dictionary §0)
├── config/                 models.yaml · routes.yaml · agents/*.yaml · scenarios/*.yaml
├── skills/<name>/SKILL.md  review playbooks (Deep Agents format)
├── schemas/                trajectory-event.schema.json · assessment-record.schema.json · openapi.json
├── src/
│   ├── domain/             review, findings, outcomes, events (Pydantic)
│   ├── data/               manifest-keyed data access
│   ├── tools/              typed tool schemas + executor
│   ├── memory/             notes, retrieval (as-of, speaker filters), graph, curator
│   ├── runtime/            LangGraph runtime, subagents, gateway chat model, context
│   ├── adapters/           OpenAI Responses adapter, fake model
│   ├── harness/            virtual clock, on-request artifacts, personas, scheduler
│   ├── governance.py · routing.py · decisions.py · sandbox.py · redaction.py · replay.py · storage.py · cli.py
│   ├── observability/      emitter, model gateway instrumentation, redaction
│   ├── evaluation/         evaluator, reviewer-baseline comparison, fairness pairs, reliability
│   └── api/                FastAPI + SSE for the console
├── tests/
└── frontend/               observability console (later initiative)
```

---

## 15. Assumptions, inventions, and open questions

### Invented for the POC
- Copperlake Bank, its products, prices, fees, offers, programs, SOPs, glossary, scripts, incentive plan, thresholds (0.75, $250, 10-customer systemic threshold, 220 wpm, 10-business-day SLA) and all automated-governance rules.
- Every person, colleague ID, team, site assignment, message, complaint and precedent.
- Background distributions, reviewer noise calibration and scanner rules.
- The vendor-style "re-transcription" and "audio recovery" services and their delays.

### Not verified in research (see research §10)
τ-bench pass^k wording; FCRA prescreen language specifics; reservist SCRA timing; PCI DSS requirement numbering; vendor internals.

### Choices between alternatives
- **Fully automated** rather than human testers (user decision) — governance in code replaces the second-level tester.
- **Phone + chat + secure message from the start** (user decision) rather than phone-first.
- **New fictional issuer** (user decision) rather than reusing CatcherAI's Lanternfield Bank.
- **Same runtime stack as CatcherAI** (Deep Agents + LangGraph, OpenAI `gpt-5.6-luna` via the Responses API behind a provider-neutral gateway) so the implementation can reuse proven patterns.
- **Desktop events** as the screen-recording substitute rather than video.
- **Three outcome decisions** rather than one verdict.
- **Deadlines and populations computed, not stored** (stored answers leak).
- **Text-only transcripts plus delayed re-transcription** rather than audio.

### Questions that would improve this (not blocking)
1. Should colleague-facing outputs (coaching notes) be generated, or only the assessment record?
2. Is collections servicing (Reg F) worth adding as a second track later?
3. Do you want scenario families for statistically meaningful per-category evaluation, or are 23 hero cases plus the background enough for the demo?
4. Should the Q01 sweep capacity and random-slice share be demo parameters in the console?
