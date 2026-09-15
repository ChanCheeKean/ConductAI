## Who you are and what we're building

You are the lead data engineer for **ConductAI**, a proof-of-concept **agentic conduct-review system** for a fictional US credit-card issuer, Copperlake Bank, N.A. It reviews phone, chat and secure-message interactions for sales and servicing misconduct, fully automated. The design foundation is done: domain research, a case catalog of 23 hero reviews plus a portfolio sweep, a data dictionary, a README describing every ecosystem, and the implementation kickoff prompt for the session after this one.

Your job in this session is to **build the data foundation the agent will be evaluated on**: the versioned knowledge corpus, the deterministic synthetic-data generator, the on-request and simulation artifacts, the memory seed, the graph projection, machine-checkable ground truth, the validator and the SQLite loader. No agent runtime, no LLM calls, no frontend.

> **Development-process subagents (not ConductAI runtime behavior):** if you delegate research, authoring, implementation, debugging or review work to subagents, use **Sonnet** by default for well-scoped work (for example one hero-case builder, one corpus family, one validator section) and gather their results back into this session. Keep consequential synthesis — schema changes, cross-case consistency, ground-truth arithmetic review — in the main session. This governs the engineering session only; it must never appear in ConductAI configuration, data or trajectories.

> **Non-negotiable: the system being prepared is fully automated.** No human testers anywhere in current-period data. Legacy human QA reviews exist only as historical labels (before 2026-10-01) and legacy run traces; automated governance is defined by `CLB-SOP-CRM-003@v4`.

---

## 1. Read these first (in this order)

| File | Why |
|---|---|
| `handoff.md` | Current state, decisions, stage plan |
| `README.md` | The foundation: use case, data/evidence/policy ecosystems, memory design, governance rules (§8), generation principles and distributions (§9), component → scenario (§10), target layout (§14) |
| `docs/design/02-case-catalog.md` | The specification for every hero: setup facts, amounts, timestamps, expected path, ground truth, traps; §0.1 effective dates; §0.2 SLA dates; §2 capability coverage; §5 background population |
| `docs/design/03-data-dictionary.md` | Every file and field, joins, output (assessment record) and ground-truth schemas, temporal fields, deliberate data-quality issues |
| `docs/research/01-domain-research.md` | What is real vs invented; which regulation text to abridge; unverified items (§10) |
| `/Users/kean/Dev/CatcherAI/data/` | **Reference implementation** of the same approach (`corpus/author_policies.py`, `generator/gen.py`, `world.py`, `background.py`, `derived.py`, `capabilities.py`, `memory_seed.py`, `precedents.py`, `validate.py`, `load_sqlite.py`). Read it to reuse structure, conventions and validator style; do not copy dispute-specific content |

---

## 2. Deliverables

1. `data/corpus/` authored by `data/corpus/author_corpus.py` (so the corpus is reproducible):
   - every document in README §8 "Corpus" with front matter `doc_id, version, effective_from, effective_to, status (active | superseded | scheduled | vacated), supersedes, superseded_by, provenance (regulation_abridged | paraphrase | invented)`;
   - regulation files are **abridged** from primary text verified in research — mark anything unverified;
   - glossary v6/v7/v8 with the exact rule differences the cases depend on (catalog §0.1, C10, C19);
   - scripts (CHC) per product/version, including the stale `CLB-CHC-CLI@v4` sentence (C04) and Spanish `CLB-CHC-FLEX` (C10);
   - SOPs with the thresholds in README §8 (panel triggers, 0.75, $250, 10 customers, 220 wpm, 10-business-day SLA, random-slice share, allowed/forbidden actions, prohibited features);
   - `data/corpus/skills/*.md` review playbooks: add-on consent, balance-transfer disclosure, credit-line increase, product change, retention, hardship & vulnerability, SCRA, complaints, multilingual review, memory hygiene, automated adjudication.
2. `data/generator/` — deterministic, stdlib-only Python, fixed seed:
   - `world.py` (issuer, products, sites, teams, colleagues, calendars, clock offsets);
   - one builder per hero case under `heroes/` (C01…C20, C02b, C07b, C11b), each creating **all** of its records together: customers, accounts, interactions, turn-level transcripts (ASR version and, where specified, the re-transcription), desktop and interaction events, offers/enrollments/product changes/plans, ledger rows, flags/preferences/incidents/config changes, CRM notes, internal comms, complaints, on-request artifacts, personas, precedents, memory notes and the ground-truth file;
   - `background.py` + `transcripts.py` + `asr_noise.py`: ~6,500 interactions with the README §9 distributions, template-grammar transcripts, ASR substitution/deletion/insertion noise weighted toward consent- and fee-critical words, ~2% diarization swaps with correct channel metadata, Spanish/code-switched bilingual-queue segments, gold labels at 3.6% prevalence, legacy QA reviews with scanner-biased selection and reviewer noise calibrated to the reference baseline (R-A ≈ 79/76, R-B ≈ 74/71, R-C ≈ 75/77 precision/recall), scanner rules and flags;
   - planted structures (README §9 table) with the exact counts in the catalog;
   - `derived.py`: business days with US bank holidays, time-zone and workstation-offset alignment, wpm from word timings, fee arithmetic, cancellation-rate statistics, SLA dates — used by the generator for ground truth and later ported into sandbox helpers;
   - `capabilities.py`: per-case `required_capabilities` and `capability_coverage.json` from catalog §2;
   - `memory_seed.py`, `precedents.py`, `graph.py` (projection per data dictionary §8), `manifest.py`;
   - `gen.py` orchestrates everything into `data/generated/` and writes `manifest.json` (paths, counts, seed, `AS_OF`, on-request delays).
3. `data/generator/validate.py` — fails loudly on:
   - schema and join violations; orphan IDs; `available_at` inconsistencies; transcripts whose turn/word timings exceed the call or overlap recording gaps incorrectly;
   - ground-truth arithmetic that doesn't reproduce with `derived.py` (fees, refunds, wpm, alignment offsets, SLA dates, populations);
   - every capability not primary in ≥ 3 hero cases;
   - hero facts drifting from the catalog (amounts, timestamps, counts, versions);
   - **discoverability checks** (README §9), including: C04 SQL finds exactly 41 affected calls plus 6 correct-warning controls; C11 COL-4421 has the highest early-cancellation rate among colleagues with ≥ 10 enrollments and COL-4425 is within one standard deviation of the program; C12 exact-phrase search finds 3 hits while the planted paraphrase set is 17 with the 2 non-misrepresentations identifiable from channel metadata or negation; C10 exactly 63 bilingual calls fall in the ASR-misrouting window; C15 9 solicited delayed opt-outs; C18 4 sales inside gaps; C16 6 post-call enrollments; background gold prevalence 3.6% ± 0.2%; reviewer precision/recall within ± 3 points of targets;
   - fairness hygiene: no prohibited attribute correlates with gold misconduct in the background beyond noise; no `is_hero`, ground-truth or simulation field reachable from agent-visible tables.
4. `data/generator/load_sqlite.py` — builds `data/generated/conduct.sqlite` with tables for all structured data and events, transcripts (turns and words), documents, corpus chunks with version metadata, memory notes, FTS5 indexes over transcripts/documents/corpus; leaves embeddings for the implementation session (or add sqlite-vec if trivial and deterministic).
5. Update `docs/design/03-data-dictionary.md` and the catalog wherever the implementation forced a precise choice (record the change and why), update `README.md` §4/§9 with actual counts, and update `handoff.md`.

Commands the session must end with working:
```bash
python3 data/generator/gen.py && python3 data/generator/validate.py
python3 data/generator/load_sqlite.py
```

---

## 3. Rules

- **The catalog is the contract.** If a hero fact is impossible or inconsistent when implemented, stop, fix the catalog and the ground truth together, and note the change in `handoff.md`. Never let data and narrative drift apart.
- **Ground truth is computed, not typed.** Amounts, dates, populations and SLA dates come from `derived.py` over the generated records.
- **Hard boundary:** `ground_truth/**` and `simulation/**` are evaluator/harness only; agent-visible tables must not contain `is_hero` in the loaded agent view (keep it only in evaluator-side tables or a separate DB).
- **Identities are obviously fake:** `@example.com/.net/.org`, `555-01xx`, masked PANs; redaction markers in transcripts where a customer reads out a card number.
- **Deterministic:** same seed → byte-identical output; no network, no LLM calls, no wall-clock reads.
- **Code quality:** plain functions and data; small modules; type hints; no dead code; follow CatcherAI's generator conventions unless this domain needs something different.
- **Background realism over volume:** transcripts should read like real servicing calls (authentication, holds, small talk, recaps), with misconduct inserted at realistic subtlety — bright-line vs judgment per the distributions.
- At the end of the stage, update `handoff.md`, then commit and push to `origin/main`; don't commit mid-stage unless asked. Ask questions only when truly blocked by a decision that is mine to make; otherwise decide, record it in `handoff.md`, and proceed.

---

## 4. Suggested order

1. Scaffold `pyproject.toml` (uv, Python 3.11+), `data/` layout, `derived.py` with tests for business days, time zones, offsets and wpm.
2. Author the corpus (`author_corpus.py`) — glossary, scripts, SOPs, products, regulation abridgements, skills.
3. `world.py` + background generator at small scale; validator skeleton (schemas, joins, `available_at`).
4. Hero builders in batches (delegate to Sonnet subagents per batch, each given the catalog section, data dictionary and `derived.py`): C01–C05, C06–C09, C10–C12, C13–C17, C18–C20 + contrast cases. Review each batch's ground truth yourself.
5. Planted structures and discoverability checks; scale the background to target volume; calibrate reviewer noise and prevalence.
6. Memory seed, precedents, on-request artifacts, personas, graph projection, capability coverage, manifest.
7. SQLite loader; full regenerate + validate; update docs and `handoff.md`.
