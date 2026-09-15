# 01 — Domain Research: Conduct Monitoring of Credit-Card Servicing Interactions

> **Status:** research checkpoint. It records what the domain looks like so the use case, data ecosystem, case catalog and memory design rest on verified ground. Architecture research (Deep Agents, LangGraph, event schemas) is phase 1 of the implementation kickoff, not this document.
>
> **Research date:** 15 September 2026. Two research threads ran in parallel; their full cited briefs are kept verbatim in [`briefs/regulatory-and-enforcement.md`](briefs/regulatory-and-enforcement.md) and [`briefs/ai-methods.md`](briefs/ai-methods.md). This document synthesizes them, corrects them where needed, and says what the design takes from each finding. The reference program summary we started from is [`../reference/reference-program-brief.md`](../reference/reference-program-brief.md).

## Source-quality legend

| Tag | Meaning |
|---|---|
| **[P]** | Primary text read or confirmed this session (statute, regulation, consent order, official product documentation, paper) |
| **[R]** | Regulator publication (supervisory highlights, bulletins, press releases) |
| **[V]** | Vendor documentation or marketing — true about their product description, not an independent accuracy claim |
| **[S]** | Secondary source (law firm alert, trade press, engineering blog) |
| **[A]** | Academic preprint not independently replicated |
| **[K]** | Domain knowledge not re-verified this session — **flagged for verification** |

---

## 1. What the reference program teaches, and where we deliberately differ

The reference program (a large issuer's GenAI call-monitoring pilot) reviews US phone servicing calls for **potential sales misconduct** using transcripts, structured call data and four reference sources (misconduct glossary, policies, sales instructions, product disclosures). Its stated results against three human reviewers: AI precision 65% / recall 78% / FP rate 17.7%, versus reviewers at 74–79% precision and 71–77% recall. It names four hard problems: class imbalance (~3.6% misconduct), human-vs-AI environment mismatch (no audio or screen recordings), scarce and subjective labels with sampling bias, and concept drift with unversioned guidelines. It uses majority voting to reduce false positives and routes every result to two levels of human testers.

| Reference program | ConductAI (this POC) | Why |
|---|---|---|
| Two levels of human testers validate every flag | **Fully automated**; an automated review panel, verifier checks, calibrated confidence and conservative defaults replace testers | User decision. Raises the bar on governance; see §6.3 for why this departs from current vendor practice |
| Output: "No Errors" or "Potential Misconduct" + reason + confidence | Three separate decisions — **customer outcome, colleague outcome, control outcome** — with evidence spans and field-level provenance | Enforcement history shows harm, individual fault and systemic cause come apart (§3) |
| US phone first; chat and non-English later | Phone, chat and secure message from the start; Spanish and code-switched calls on a bilingual queue | User decision; cross-channel continuity and language fairness are where single-call classifiers fail |
| Screen recordings unavailable to the model | **Desktop event stream** as the machine-readable substitute for screen recordings | The reference's "undisclosed product switching" example is undetectable without it |
| Guideline versioning is an open question | Every glossary, script, policy and disclosure is **versioned with effective dates**; retrieval is as-of the interaction date | Named concept-drift risk; real rules reverse (§2.3) |
| Majority voting over classifications | Deterministic cross-source checks first; LLM reasoning for residual ambiguity; adversarial panel for high-impact findings; confidence derived from verifier signals, not self-report | Majority voting can hurt on systematic blind spots; stated LLM confidence doesn't track correctness (§6.2) |
| Transcript-level classification | Interaction-, colleague- and population-level findings (patterns, stale scripts, unapproved material) | Two major enforcement actions name incentive design, not rogue agents, as root cause (§3) |

## 2. The regulatory frame (US credit-card servicing and sales)

### 2.1 The charging theory: UDAAP
Dodd-Frank §§1031/1036 prohibit unfair, deceptive or abusive acts or practices by covered persons, including card issuers and their service providers **[P]**. *Unfair*: substantial injury not reasonably avoidable and not outweighed by benefits. *Deceptive*: a representation or omission likely to mislead a reasonable consumer, material to the decision. *Abusive*: materially interferes with understanding a term, or takes unreasonable advantage of a consumer's lack of understanding, inability to protect their interests, or reasonable reliance **[P]**. Every CFPB card add-on enforcement action found used UDAAP **[P]**. "Abusive" is the least settled prong across CFPB leadership changes **[S]**.

**Design consequence:** the glossary categories (MC-01…MC-11) are behavioral patterns mapped to UDAAP prongs, not product-specific keyword lists. Bright-line items (missing disclosure, enrollment timestamp before consent) and judgment items (pressure, vulnerability) are labeled separately because reviewer agreement differs sharply between them.

### 2.2 Rules that make specific cases possible

| Rule | What it requires | Where it appears |
|---|---|---|
| Reg Z §1026.51 ability to pay **[P]** | No new account or **credit-line increase** without considering independent ability to pay | CLI flows (C02b, C03, C04) — background generator must record income/obligation checks |
| Reg Z §1026.56 over-the-limit opt-in **[P]** | No over-limit fee without affirmative opt-in; revocable | Background consent scenarios |
| Reg Z §1026.9 change in terms **[K, high confidence]** | 45 days' written notice before increasing significant terms | Background: colleague says a rate change is immediate |
| Reg Z §1026.13 billing errors **[P]** | Error-resolution procedures once a billing-error notice is received | Background: colleague discourages a dispute (MC-10) |
| Reg Z §1026.52 penalty fees — **$8 late-fee rule (2024) vacated 15 Apr 2025** **[P/S]** | Pre-2024 inflation-indexed safe harbors are back | C07 stale memory; a real, dated example of rule reversal |
| FCRA permissible purpose; hard vs soft inquiries **[P for enforcement use, K for mechanics]** | Credit reports pulled only with permissible purpose; hard inquiries follow a consumer-initiated credit request | C03, C04; US Bank 2022 and BofA 2023 cite FCRA for unauthorized applications |
| FCRA prescreened firm offers **[K]** | "Pre-approved" language is tied to firm offers of credit | C19 |
| ECOA / Reg B **[P]** | Prohibited bases include age, national origin, marital status; adverse-action notices within 30 days | Fairness guardrails (C10, C14); background CLI declines |
| SCRA 6% cap **[P/S]** | Pre-service obligations **including credit cards** capped at 6% (interest broadly defined) during military service, excess forgiven not deferred, on written request with orders; some provisions are strict liability | C09 |
| TCPA / Telemarketing Sales Rule **[P]** | Consent for certain outbound calls; material terms disclosed before obtaining consent to pay | Outbound-sale policy (C02, C02b); invented SOP operationalizes it |
| GLBA / authentication **[P/S]** | Verify identity before disclosing nonpublic information or changing the account | Background MC-11/authentication scenarios |
| CFPB LEP statement (Jan 2021) **[P]** | Risk-based language access; collecting language preference does not itself violate ECOA | C10 |
| FinCEN FIN-2022-A002 elder exploitation **[P]** | Behavioral and financial red flags; the failure is often *not escalating* | C14 behavioral-indicator list |
| OCC/interagency incentive-compensation guidance (2010) **[P]** | Incentives must balance risk and reward | C06, C11, C12 incentive context |

### 2.3 Rules move — sometimes backwards
The $8 late-fee rule was finalized in March 2024, challenged within days and vacated by consent judgment on 15 April 2025 **[P/S]**. The CFPB terminated its Navy Federal overdraft order on 30 June 2025 and dropped its Capital One 360 suit in February 2025 **[S]**. A monitoring system with a static rule library is silently wrong after a reversal; ground truth must be date-versioned. This is why every corpus document carries `effective_from / effective_to / status ∈ {active, superseded, scheduled, vacated}` and why C07, C10, C19 exist.

## 3. Enforcement history: what agents actually did

Full detail and citations: [`briefs/regulatory-and-enforcement.md`](briefs/regulatory-and-enforcement.md) §2.

| Action | Conduct | Relief | Lesson for the design |
|---|---|---|---|
| Capital One 2012 **[P]** | Vendor call centers told customers add-ons were required to activate the card, enrolled without consent, claimed credit-score benefits | ~$140M refunds + $25M CFPB + $35M OCC penalties | MC-02, MC-03, MC-05 are the historical core |
| Discover 2012 **[P]** | Deceptive telemarketing of payment protection, score tracking, ID theft protection | ~$200M refunds + $14M | Add-on telesales scripts need disclosure checks |
| JPMorgan Chase 2013 **[P]** | Billed for identity-protection services not delivered | ~$309M restitution + $80M penalties | "Promise vs system state" requires structured data |
| Bank of America 2014 **[P]** | Deceptive add-on marketing; billed for monitoring not performed | ~$727M relief + $45M | Same |
| Citibank 2015 **[P]** | Debt-protection and monitoring add-ons misrepresented (monitoring said to alert on fraudulent purchases) | ~$700M relief + $35M | Capability misrepresentation needs product fact sheets |
| Synchrony 2014 **[P]** | Deceptive debt-cancellation telesales **and** Spanish-speaking / Puerto Rico customers excluded from settlement offers (ECOA) | $225M total relief incl. $56M add-on refunds | Language is a fairness axis at the *offer* layer too |
| Wells Fargo 2016 **[P]** | 1.5M deposit and 623K credit-card accounts opened without authorization to meet quotas | $185M penalties | Quota-driven, systemic |
| US Bank 2022 **[P]** | Cards and lines opened without consent under sales goals; FCRA permissible-purpose violations | $37.5M penalty + remediation | CFPB names **incentive design** as root cause → population-level findings |
| Bank of America 2023 **[P]** | Cards opened without authorization; promised rewards withheld; double NSF fees | $150M penalties + $100M restitution | Servicing promises not honored in systems |
| American Express 2025 **[S]** | Small-business card sales using fabricated EINs; misleading tax/points pitches | $230M DOJ/Fed | Data falsification is a higher tier than mis-selling (MC-11 severity) |

**Unverified:** a standalone 2012 American Express order separate from the 2017 order; any Credit One Bank enforcement order. Do not cite either.

Patterns the enforcement record shows and a per-call classifier misses:
1. **Harm, fault and cause diverge.** Customers were harmed by vendor scripts, incentive plans and billing systems as often as by individual colleagues → three outcome decisions (catalog §1.1).
2. **The unit of misconduct is often a population.** Remediation orders cover millions of accounts sharing one practice → C04, C11, C12 compute affected populations.
3. **Detection came mostly from examinations, not complaints** **[P/R]** → frame the system as an always-on examiner (Q01 sweeps the whole week), not a complaint triage tool; complaints are one trigger among several.

## 4. Where misconduct arises in card servicing

Thirteen flows with documented or practitioner-known risk ([brief](briefs/regulatory-and-enforcement.md) §3): balance transfers (fee and post-promo APR omitted), credit-line increases (hard pull described as soft; no ability-to-pay check), product changes (silent rewards forfeiture, higher fee without consent), add-ons (silent enrollment, "required to activate"), retention (inaccurate consequences of closing, not honoring cancellation), hardship programs (steering, selling to hardship customers), fee waivers (conditional waivers), authorized users (unauthenticated adds), paperless/autopay (enrollment without consent), travel protection cross-sell, installment plans (fee framed as "no interest"), cash advances, rewards redemption.

The POC products (catalog §0) were chosen to cover balance transfers, CLI, product change, two add-on types, retention, hardship, fee waivers, installment plans, SCRA and complaints — the flows with the densest enforcement history plus the reference program's three highlighted error categories (credit-reporting inaccuracy, enrollment without consent, leveraging cancellation).

## 5. How the industry monitors conduct today

### 5.1 Human QA
Legacy programs sample a small share of interactions per colleague (commonly low single-digit percent) and score them on scorecards that mix binary must-pass compliance items with scaled soft-skill items **[K]**. Red-flag phrase libraries exist but are proprietary; no public glossary was found, so ours is explicitly invented **[S]**. Automated programs move toward near-100% coverage with humans on flagged calls, appeals and calibration **[V]**.

### 5.2 Vendors
NICE Enlighten (pre-built behavior models incl. vulnerable-customer detection), CallMiner Eureka, Verint (mechanism undisclosed), Observe.AI and Level AI (client-configurable rubrics scored by an AI layer), Cresta and Balto (real-time in-call guidance), AWS Contact Lens (rule-triggered alerts plus natural-language GenAI categories), Azure AI Language (conversation-level PII redaction), Google Conversational Insights **[V]**. The credible pattern is configurable rubrics over a tagging backbone, not pure keyword spotting and not a bare LLM judge. **Genesys documents that AI-scored evaluations require human approval** **[V/P]** — the industry has not shipped fully automated conduct verdicts. Our design is ahead of vendor practice and must carry the governance burden in code.

### 5.3 The monitoring lifecycle we model
Interaction → recording and ASR (with model routing by language) → PII/PCI redaction → selection (scanner flags, risk ranking, protected random slice) → review → findings → remediation, coaching, control actions → complaint and outcome feedback → precedents and memory. The legacy scanner and legacy human QA labels exist in the data as baselines (catalog §3, §5).

## 6. AI methods research that shapes the design

Full detail and citations: [`briefs/ai-methods.md`](briefs/ai-methods.md).

### 6.1 No published system does cross-source conduct review end to end
No paper or open system joins transcripts, desktop events, enrollment/fee ledgers and versioned policy into a misconduct verdict **[A/S]**. The closest analogues: τ²-bench's dual-control evaluation (reconciling two independent action streams) **[A]**; "corrupt success" procedure-aware evaluation (right outcome, non-compliant path) **[A]**; RIRAG/ObliQA regulatory retrieval with obligation-level grounding metrics **[A]**; graph analytics for fraud rings **[S]**. We assemble the design from these.

### 6.2 Findings that constrain the design

| Finding | Evidence | Design decision |
|---|---|---|
| Single LLM judges are unreliable and poorly calibrated in-domain | 541k-judgment study (arXiv 2606.19544) **[A]**; overconfidence studies **[A]** | No single-pass verdicts on high-impact findings; panel + verifier |
| **Stated LLM confidence does not track behavior** — models rarely abstain even when it is optimal | arXiv 2601.07767, 2606.29490 **[A]** | The 0.75 threshold applies to a **computed** confidence (verifier pass rate, citation verification, evidence coverage, panel agreement), never a model's self-reported number |
| Majority voting can hurt when errors are correlated | arXiv 2608.11403 **[A]** | Adversarial roles with different briefs, not k identical samples; measure before adopting |
| Models find the right document but mislocate spans; 13–21% citation hallucination even with RAG | arXiv 2606.07130, 2606.00898 **[A]** | Every evidence quote and policy clause is **deterministically verified** against source (turn ID + substring) before a finding can be recorded |
| ASR substitution errors flip meaning ("no"/"know", "fee"/"free"); LLMs degrade monotonically with WER | arXiv 2109.12306, 2404.09754 **[A]** | ASR confidence is surfaced; findings resting on low-confidence spans require re-transcription (C01, C10) |
| **Diarization errors (10–20% DER in overlapping speech) can flip who said it** — likely the highest-leverage transcript risk | arXiv 2406.17124 **[A]**; practitioner reports **[S]** | Segment-level diarization confidence plus channel-separated speaker metadata; C12 plants a speaker swap |
| Chunk-by-phase extraction then whole-interaction reconciliation bounds context without losing cross-phase facts | rubric-grading literature **[A]**, synthesis **[K]** | Two-pass pattern: extract claims/events per call phase with turn IDs → reconcile against records |
| Transcripts are untrusted input; injected text in content can steer agents | OWASP, AgentDojo (arXiv 2406.13352) **[P/A]** | Transcripts and CRM notes are data; no agent with raw transcript context holds unmediated write tools; injection eval cases (C20) |
| PAN/CVV must not persist in transcripts | PCI DSS guidance via vendors **[S]** — verify against the PCI SSC standard | Deterministic redaction before any model or index sees text |
| LLM contact-center QA shows counterfactual unfairness on identity/accent cues | arXiv 2602.14970 **[A]** | Matched-pair fairness eval; language, accent, age and ASR confidence are prohibited risk features (Q01) |
| Temporal knowledge graphs invalidate rather than delete (bi-temporal) | Graphiti docs **[V]** — maintainer claims, not benchmarked | Memory notes and graph hypotheses carry valid-time and record-time; retraction keeps history |
| At 3–4% prevalence, PR curves not ROC; high-recall operating points yield low precision | npj Digital Medicine; RARE25 **[A]** | Staged review (cheap selection → expensive review); report precision/recall/FPR per category and at interaction vs colleague level |
| Benchmarks ship with label bugs (τ²-bench-verified) | **[P]** | `validate.py` discoverability checks; ground truth audited, not LLM-generated |

### 6.3 pass^k
τ-bench defines pass^k as the probability that **all k** independent trials of a task succeed, as opposed to pass@k (any of k) **[K — the research thread did not retrieve the τ-bench paper text; verify against arXiv 2406.12045 before citing]**. We use it because a conduct finding that flips across runs is itself a control defect.

## 7. Hard problems the data must contain

| Problem | How the dataset plants it |
|---|---|
| Rare positives (~3.6%) | Background gold prevalence 3.6% |
| Human-vs-AI environment mismatch | Desktop events replace screen recordings; audio is only reachable via re-transcription/recovery tools with delays |
| Transcript quality | ASR word confidence, WER by segment, wrong-language ASR model window (C10), recording gaps (C18) |
| Diarization errors | Segment speaker confidence + channel metadata; planted swaps (C12, background) |
| Subjective, noisy labels | Three legacy reviewers with calibrated noise matching the reference baseline; ~5% flawed precedents |
| Sampling bias | Legacy QA sampled by scanner flags; Q01 protected random slice |
| Concept drift and versioning | Glossary v6→v7→v8, CLI v5→v6, CHC-BT v4→v5, stale CHC-CLI v4, vacated late-fee rule |
| Cross-channel continuity | Chat → callback → phone chains (C02, C08, C15) |
| Incentive-driven and systemic misconduct | Q4 incentive plan; team cheat sheet (C12); colleague pattern (C11) |
| Monitor gaming | Speed-read disclosures, "mark compliant" injection (C20) |
| Multilingual fairness | Bilingual queue, Spanish ASR misrouting, prohibited language features |

## 8. Non-obvious insights worth building the demo around

1. **Harm, fault and cause are three decisions.** The same interaction can require refunding the customer, clearing the colleague and opening a control gap (C04, C15). Collapsing them is how monitoring programs produce both unfair findings and missed remediation.
2. **Benefit of the doubt runs both ways.** Below the confidence threshold the customer is remediated *and* the colleague gets no adverse finding (C14, C18). That asymmetry is what makes full automation defensible.
3. **The approved script can be the misconduct.** A colleague reading CHC-CLI v4 verbatim gave inaccurate credit information to 41 customers (C04).
4. **"Screen recording" evidence is where the worst cases hide.** The words were polite; the product change was silent (C06). Enforcement history is full of promises that systems didn't honor.
5. **A transcript is a claim about audio, not the audio.** "No, I don't need that" and "Oh, I do need that" differ by one ASR substitution (C01); diarization can move a sentence from customer to colleague (C12).
6. **The date that governs is the interaction date.** A scanner upgraded on 1 November re-flagged October calls under rules that didn't exist yet (C10).
7. **Rules reverse.** The $8 late-fee cap came and went; stale memory that still enforces it would flag a colleague for telling the truth (C07).
8. **Patterns are leads, not evidence.** A 61% early-cancellation rate justifies a lookback; each substantiated interaction still needs its own transcript evidence, and a teammate with high sales is not implicated (C11/C11b).
9. **Paraphrase defeats phrase lists.** One supervisor's "basically free" became 17 wordings across five colleagues; keyword search finds 3 (C12).
10. **Age is never the reason — behavior is.** Vulnerability findings must cite what the customer said and did, and memory that encodes age must be purged (C14).
11. **The most careful monitor is the one the colleague is talking to.** Monitoring changes behavior; robustness to gaming and injection is a requirement, not a hardening task (C20).
12. **A random slice keeps the selector honest.** Risk ranking alone makes measured prevalence a function of the ranker; the reference program's sampling-bias problem is solved by design (Q01).
13. **Fully automated conduct verdicts are ahead of vendor practice.** Genesys requires human approval of AI scores; replacing that step demands deterministic governance code, computed confidence and a complete audit trail.

## 9. Design implications (carried into README and the kickoff prompt)

- Hybrid control: deterministic graph skeleton for routing record, recording integrity, as-of retrieval, citation verification, governance gates and write gates; adaptive Deep Agent reviewer inside.
- Two-layer evidence: deterministic cross-source checks (timestamps, ledgers, flags, word timings) first; LLM judgment for residual ambiguity.
- Computed confidence from verifier signals; 0.75 threshold for adverse colleague findings; customer-protective default.
- Evidence spans verified by turn ID and substring; policy citations verified by `doc_id@version` and clause.
- Re-transcription, audio recovery, colleague statements and customer replies are harness events with `available_at`; runs suspend and must decide by the SLA-derived latest safe decision time.
- Transcripts, chat, secure messages and CRM notes are untrusted; injection attempts are flagged and quoted, never followed.
- Deterministic PII/PCI redaction before indexing and model calls.
- Fairness: prohibited features enforced in code for both customers and colleagues; matched-pair eval.
- Memory: bi-temporal notes and graph hypotheses; supersede / retract / consolidate / purge / expire; colleague-scoped notes are evidence-backed, time-bounded, and never imported across colleagues.
- Evaluation: interaction-level precision/recall/FPR vs the legacy reviewer baseline; per-category and colleague-level recall; capability-usage checks from trajectories; pass^k; cost per interaction.

## 10. Unverified or conflicting items (resolve before or during data generation)

| Item | Status | Impact |
|---|---|---|
| τ-bench pass^k definition | [K] | Terminology only |
| FCRA prescreen "firm offer" language rules for "pre-approved" | [K] | C19 relies on the invented glossary v7, not on FCRA text |
| When SCRA reservist protections begin relative to orders | not verified | C09 outcome independent of it |
| Reg F "7-in-7" call frequency | [S] | Out of scope (no collections in POC) |
| PCI DSS requirement numbering for sensitive authentication data in recordings | [S] | Redaction design only |
| ECOA authorized-user reporting mechanics | [K] | Not used by hero cases |
| Standalone 2012 American Express order; any Credit One order | not found | Do not cite |
| Vendor internal decision logic (Verint, CallMiner) | undisclosed | Baseline description only |
| Graphiti retrieval-quality claims | maintainer claims | Pattern borrowed, not the dependency |

## Sources

The complete source lists, with URLs and per-source quality tags, are at the end of each brief:
- [`briefs/regulatory-and-enforcement.md` — Sources](briefs/regulatory-and-enforcement.md#sources) (CFPB/OCC/DOJ/FinCEN/Federal Register primary documents; law-firm and trade-press coverage)
- [`briefs/ai-methods.md` — Sources](briefs/ai-methods.md#sources) (papers, official vendor documentation, secondary engineering write-ups)

Key primary sources cited above: CFPB enforcement pages for Capital One (2012), Discover (2012), American Express (2017), Citibank (2015), Bank of America (2014, 2023), Synchrony (2014), US Bank (2022), Wells Fargo (2016); OCC JPMorgan Chase release (2013); CFPB Credit Card Penalty Fees Final Rule page and Holland & Knight / Goodwin coverage of its 2025 vacatur; CFPB UDAAP examination procedures (2023); eCFR 12 CFR 1026.56 and Part 1002; CFPB LEP statement (2021); FinCEN FIN-2022-A002; DOJ SCRA 6% cap guidance and OCC Comptroller's Handbook (SCRA); OCC incentive-compensation guidance (2010); Genesys Cloud AI scoring documentation; Azure AI Language conversation PII documentation; AWS Contact Lens documentation; arXiv 2506.07982 (τ²-bench), 2603.03116, 2409.05677 (RIRAG), 2606.19544, 2601.07767, 2606.29490, 2608.11403, 2606.07130, 2606.00898, 2406.17124, 2602.14970, 2406.13352 (AgentDojo), 2604.11171 (RARE25).
