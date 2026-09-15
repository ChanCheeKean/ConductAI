# Corpus contract

The single list of corpus documents, versions, effective dates and **clause numbers** that the generator, hero ground truth and validator depend on. `author_corpus.py` must produce exactly these documents with these headings; ground truth cites `doc_id@version §clause` from this table, and `validate.py` checks every cited clause exists as a heading (`## §<clause> …` or `### §<clause> …`) in the file.

File layout: `data/corpus/<family>/<doc_id>@<version>.md` (families: `regulation`, `policies`, `glossary`, `scripts`, `products`, `incentives`) and `data/corpus/skills/<skill>.md`. `data/corpus/index.json` lists every document's front matter.

Front matter keys (YAML-style, one `key: value` per line): `doc_id, version, title, family, effective_from, effective_to, status, supersedes, superseded_by, provenance, owner`. Empty values are written as `""`. Dates are ISO `YYYY-MM-DD`. `effective_to` is the last day in force. Status is evaluated **as of AS_OF 2026-11-16**: `active | superseded | scheduled | vacated`.

## Regulation (`provenance: regulation_abridged` unless marked)

| doc_id@version | effective | status | Clauses that cases cite |
|---|---|---|---|
| `REG-UDAAP@2010` | 2011-07-21 → | active | §1031(b) deceptive, §1031(c) unfair, §1031(d) abusive, §1036 prohibited acts |
| `REGZ-1026.51@2010` | 2010-02-22 → | active | §1026.51(a) ability to pay (incl. credit line increases) |
| `REGZ-1026.9@2010` | 2010-08-22 → | active | §1026.9(c) change-in-terms 45-day notice (K, marked unverified detail) |
| `REGZ-1026.13@2010` | 2010-02-22 → | active | §1026.13 billing-error resolution |
| `REGZ-1026.56@2010` | 2010-02-22 → | active | §1026.56 over-the-limit opt-in |
| `REGZ-1026.52@pre-2024` | 2010-08-22 → | active | §1026.52(b) penalty-fee safe harbors, inflation-indexed (no dollar figure asserted beyond "indexed annually") |
| `REGZ-1026.52@2024-03-15` | 2024-05-14 → 2025-04-15 | **vacated** | §1026.52(b)(1)(ii)(B) $8 late-fee safe harbor for larger issuers; note: vacated by court order 2025-04-15, pre-2024 safe harbors apply |
| `FCRA-INQUIRY@2003` | 2003-12-04 → | active | §604 permissible purpose; §INQ-1 hard vs soft inquiry mechanics (`provenance: paraphrase`, marked not verified) |
| `FCRA-PRESCREEN@2003` | 2003-12-04 → | active | §604(c) prescreened firm offers of credit; §615(d) prescreen disclosure (`provenance: paraphrase`, marked not verified) |
| `REGB-1002@2011` | 2011-12-30 → | active | §1002.2(z) prohibited basis (incl. age, national origin); §1002.4(a) discrimination prohibited; §1002.9 adverse action |
| `SCRA-3937@2003` | 2003-12-19 → | active | §3937(a) 6% maximum rate on pre-service obligations incl. credit cards; §3937(b) written notice + orders; interest above 6% forgiven |
| `TSR-310@2016` | 2016-06-13 → | active | §310.3(a)(1) disclose material terms before the customer consents to pay; §310.4(a)(7) express informed consent |

## Copperlake policies and SOPs (`provenance: invented`)

| doc_id@version | effective | status | Clauses that cases cite (content that must be present) |
|---|---|---|---|
| `CLB-SOP-SAL-001@v3` | 2025-01-06 → 2026-05-31 | superseded | same structure as v4 without §5.3 numeric limit ("disclosures must be clear") |
| `CLB-SOP-SAL-001@v4` | 2026-06-01 → | active | §3.1 affirmative consent = a clear, verbal yes to a specific named product **after** its price and material terms; minimal responses ("mm-hmm", "uh-huh", "okay") to a statement or tag question ("…okay?") are **not** affirmative consent · §3.2 price and material terms before consent · §4.1 enrollments are submitted during the interaction, after consent; an enrollment submitted after the interaction ends has no consent · §5.3 required disclosures must be delivered clearly; delivery faster than **220 words per minute** is not clear · §5.4 a customer question about price or terms must be answered before any enrollment · §6.1 no sale may be conditioned on, or bundled with, a servicing request or fee waiver |
| `CLB-SOP-SAL-002@v3` | 2025-09-02 → | active | §3.1 no sales on outbound servicing calls · §3.2 **callback exception**: permitted only if (a) the customer requested the callback, (b) the callback purpose names the same product/offer that is sold, (c) the call is placed within **3 business days** of the request, (d) consent to call is recorded |
| `CLB-SOP-SRV-002@v2` | 2025-03-03 → | active | §2.1 one courtesy late-fee waiver per rolling 12 months, eligibility = no courtesy waiver in prior 12 months · §3.1 a waiver is never conditional on any purchase or enrollment |
| `CLB-SOP-SRV-003@v5` | 2026-02-02 → | active | §2.1 a complaint is any expression of dissatisfaction about a product, service, fee or colleague, whether or not the word "complaint" is used · §3.1 log the complaint in the same interaction with `received_at` = when it was expressed; disposition `COMPLAINT` · §3.2 acknowledge within 5 business days · §3.3 the validity of the underlying fee does not remove the duty to log |
| `CLB-SOP-SRV-004@v2` | 2026-04-06 → | active | §2 remediation matrix rows: §2.1 fee misrepresented → refund the difference between charged and represented fee + offer cancellation with full fee refund within 30 days (BT) · §2.2 undisclosed product change → reverse after customer confirmation, restore rewards, honor the represented outcome (e.g. waive the annual fee) · §2.3 enrollment without consent or unverifiable consent → reverse enrollment and refund premiums · §2.4 sale to a protected situation → reverse the plan/product, refund fees · §2.5 cancellation not honored → honor after confirmation, refund annual fee if inside the cardholder-agreement window; do not claw back retention credits · §2.6 inaccurate credit-reporting statement on an authorized inquiry → correction letter; never request deletion of an authorized inquiry · §2.7 upgrade with vulnerability indicators → reverse upgrade, refund annual fee, support letter · §2.8 complaint not logged → log with original received date · §2.9 solicitation after opt-out → suppress solicitation; keep accepted products unless the customer asks to reverse · §2.10 customer choice: where reversal could leave the customer worse off, offer and wait for the customer's choice |
| `CLB-SOP-VUL-001@v2` | 2025-11-03 → | active | §3.1 indicator types: (a) confusion about who is calling or the purpose of the call, (b) reliance on a third party for financial decisions, (c) inability to restate key terms, (d) repeated deferential assent ("whatever you think"), (e) disclosed financial hardship (job loss, reduced income), (f) bereavement or serious illness · §3.2 when two or more indicator types are present, pause any sale and offer a callback or trusted-contact involvement · §4.1 no credit-product sales (Flex Installments, balance transfers, CLI, upgrades) to customers in an active Hardship Relief Plan · §5.1 age, birth year and assumed age are never indicators |
| `CLB-SOP-SCRA-001@v3` | 2025-06-02 → | active | §2.1 trigger: any mention of military orders, active duty, mobilization or deployment · §3.1 open an SCRA benefits review in the same interaction · §3.2 explain that the 6% cap applies to pre-service obligations including credit cards · §4.1 eligibility is decided by the SCRA benefits team, not the colleague |
| `CLB-POL-CLI@v5` | 2024-02-01 → 2026-09-30 | superseded | §2.1 all customer-requested credit line increases use a soft inquiry · §3.1 ability to pay (income, obligations) |
| `CLB-POL-CLI@v6` | 2026-10-01 → | active | §2.1 soft inquiry **unless** tenure < 12 months **or** requested increase > $5,000, in which case a hard inquiry · §2.2 colleagues must tell the customer before submission when a hard inquiry applies · §3.1 ability to pay · §9 change record: "CHC-CLI update: pending" |
| `CLB-SOP-CRM-001@v4` | 2025-03-03 → 2026-08-31 | superseded | §3 selection with 5% random slice · §4 15-business-day SLA |
| `CLB-SOP-CRM-001@v5` | 2026-09-01 → | active | §3.1 weekly capacity; §3.2 **10%** of capacity is a seeded stratified random slice by channel, seed `20261116`; §3.3 permitted risk signals: sale or enrollment event, outbound sale, early cancellation, complaint within 7 days, recording gap, protected-situation flags, scanner flags, prior substantiated findings in 90 days; §3.4 prohibited selection features (customer age, language, accent, ASR confidence, site, colleague demographics) · §4.1 decide within **10 business days** of the later of the interaction date and the selection/trigger date; weekends and US bank holidays excluded |
| `CLB-SOP-CRM-003@v3` | 2025-03-03 → 2026-09-30 | superseded | human tester approval of every adverse finding (legacy) |
| `CLB-SOP-CRM-003@v4` | 2026-10-01 → | active | §3.1 panel trigger (A): severity high and any of remediation > $250, vulnerability/hardship, rights misinformation, colleague-level pattern, systemic population ≥ 10 · §3.2 trigger (B): computed confidence of an adverse finding in [0.60, 0.85) · §3.3 panel roles: customer advocate, colleague advocate, adjudicator · §4.1 computed confidence components (verifier pass rate, citation verification, evidence coverage, transcript quality at decisive spans, panel agreement); self-reported confidence never gates · §5.1 adverse colleague finding requires ≥ **0.75**; below → `no_adverse_finding`, coaching and enhanced monitoring allowed · §5.2 customer remediation when harm plausible (≥ 0.50) or consent unverifiable · §5.3 systemic record requires a recorded population query · §6.1 allowed automated actions (README §8 list) · §7.1 forbidden actions (employment/disciplinary/compensation, bank-initiated closure, deletion of authorized inquiries, contacting regulators or third parties, prohibited bases) |
| `CLB-SOP-CRM-004@v2` | 2026-01-05 → | active | §2.1 prohibited features for customers (age/birth year, language, accent, national origin, ASR confidence as risk, site) · §2.2 prohibited for colleagues (demographics, site, team membership as evidence) · §3.1 a colleague pattern may not be extended to teammates |
| `CLB-SOP-CRM-005@v2` | 2026-01-05 → | active | §2 note lifecycle (active, superseded, retracted, archived, purged) · §3.1 supersede when a governing source changes; set `valid_to` · §3.2 retract when the note was wrong from the start · §4.1 colleague-scoped notes: evidence-backed, time-bounded, one colleague, never imported to teammates · §5.1 purge notes relying on a prohibited basis; keep a tombstone · §6.1 consolidate raw observations into one validity-bounded note with sources |

## Misconduct glossary (`provenance: invented`)

| doc_id@version | effective | status | Rule differences the cases depend on |
|---|---|---|---|
| `CLB-GLOSS@v6` | 2025-07-01 → 2026-06-30 | superseded | §MC-03.2: "pre-approved" or "pre-qualified" stated by a colleague is **always** MC-03 · §MC-03.3: "no interest"/"interest-free" for a fee-based plan permitted if the fee is disclosed in the same turn |
| `CLB-GLOSS@v7` | 2026-07-01 → 2026-10-31 | superseded | §MC-03.2: "pre-approved" is **permitted** when a prescreened firm offer exists for the customer and is displayed on the colleague desktop; otherwise MC-03 · §MC-03.3 unchanged from v6 |
| `CLB-GLOSS@v8` | 2026-11-01 → | active | §MC-03.2 as v7 · §MC-03.3: "no interest"/"interest-free" framing for a fee-based plan is **prohibited** even when the fee is disclosed |

All three versions contain §MC-01 … §MC-11 (definition, red flags, exceptions, bright-line vs judgment), and these clauses: §MC-02.1 minimal response to a statement or tag question is not affirmative consent; §MC-02.2 enrollment submitted outside the interaction; §MC-04.1 required disclosure omitted; §MC-04.2 disclosure delivered unclearly (speed above SOP limit); §MC-05.1 specific numeric credit-score predictions ("drop a hundred points") are MC-05; §MC-05.2 describing a hard inquiry as having no credit impact; §MC-06.1 conditioning a waiver or servicing outcome on a sale; §MC-06.2 failing to process a clear cancellation request; §MC-07.1 sale on outbound call outside the callback exception; §MC-08.1 product change without disclosing rewards/benefit/fee consequences; §MC-09.1 sale during active hardship or after protected-situation indicators; §MC-10.1 misinformation about SCRA, complaint or dispute rights; §MC-10.2 failing to log a complaint; §MC-11.1 CRM note or disposition contradicts the interaction; §EX-1 general statements about credit factors ("closing could affect utilization and length of history") are not MC-05.

## Colleague handling cards / scripts (`provenance: invented`)

| doc_id@version | effective | status | Content cases depend on |
|---|---|---|---|
| `CLB-CHC-CLI@v3` | 2024-02-01 → 2026-03-01 | superseded | §2.1 "This request will not impact your credit score." |
| `CLB-CHC-CLI@v4` | 2026-03-02 → | active (**stale**: never updated for CLI v6) | §2.1 exact sentence **"This request will not impact your credit score."** · §2.2 income and obligations questions |
| `CLB-CHC-BT@v4` | 2025-05-05 → 2026-10-14 | superseded | §2.1 read promo APR, promo months and go-to APR · §2.2 read the transfer fee as a percentage |
| `CLB-CHC-BT@v5` | 2026-10-15 → | active | §2.1 as v4 · §2.2 read the transfer fee as a percentage **and** the dollar amount for the requested transfer |
| `CLB-CHC-PC@v3` | 2025-08-04 → | active | §2.1 disclose rewards impact (conversion rate and value) · §2.2 disclose benefits removed (e.g. trip protection) · §2.3 obtain explicit consent to the named product change |
| `CLB-CHC-ADDON-CS@v3` | 2025-10-06 → | active | §2.1 exact price statement **"eighty-nine cents for every hundred dollars of your ending statement balance, and you can cancel anytime"** · §2.2 ask "Would you like me to add CardShield?" and wait for a clear yes |
| `CLB-CHC-ADDON-CW@v2` | 2025-10-06 → | active | §2.1 "CreditWatch Plus is $14.99 a month and you can cancel anytime" · §2.2 ask and wait for a clear yes |
| `CLB-CHC-FLEX@v2` | 2026-04-06 → | active | §2.1 state the fixed monthly plan fee as a percentage and a dollar amount · §2.2 do not describe the plan as "no interest" (aligned early to v8) |
| `CLB-CHC-FLEX-ES@v2` | 2026-04-06 → | active | Spanish version of the same card (§2.1, §2.2) |
| `CLB-CHC-RET@v2` | 2025-08-04 → | active | §2.1 process a close request no later than the customer's second request · §2.2 at most one retention offer · §2.3 no credit-score predictions; general factors only |

## Products (`provenance: invented`)

| doc_id@version | effective | Content cases depend on |
|---|---|---|
| `CLB-PRD-CARDHOLDER-AGREEMENT@v9` | 2025-01-06 → | §4.2 late fee up to $32 · §4.3 returned-payment fee $29 · §6.1 annual fee refunded in full if the account is closed within **30 days** of the annual fee posting · §7.1 product changes convert rewards at the conversion rate in the product fact sheet |
| `CLB-PRD-EVERYDAY-CASH@v4` | 2025-01-06 → | no annual fee; 1.5% cash back; no trip protection |
| `CLB-PRD-VOYAGER@v5` | 2025-01-06 → | §1 $95 annual fee; miles; §3 trip protection on travel purchased with the card; §5 product change to a cash-back card converts miles at **0.5 cents per mile** |
| `CLB-PRD-SUMMIT@v3` | 2025-01-06 → | $450 annual fee, billed on upgrade |
| `CLB-PRD-FOUNDATION@v2` | 2025-01-06 → | secured card |
| `CLB-PRD-CARDSHIELD@v3` | 2025-10-06 → | §2.1 premium **$0.89 per $100 of the ending statement balance** each month · §2.2 charged whenever the ending statement balance is above $0, **including for customers who later pay in full** · §3 cancel anytime; no premium after cancellation |
| `CLB-PRD-CREDITWATCH@v2` | 2025-10-06 → | §2.1 $14.99 per month, first fee billed on enrollment |
| `CLB-PRD-FLEX@v2` | 2026-04-06 → | §2.1 fixed monthly plan fee instead of interest; 12-month plans **1.72%** of principal per month; §2.2 fee rounded to the cent |
| `CLB-PRD-BT-OFFERS@v6` | 2026-09-01 → | `OFR-BT-12-3` 0% for 12 months, 3% fee · `OFR-BT-15-3` 0% for 15 months, 3% fee, promotional segment only · `OFR-BT-15-5` 0% for 15 months, 5% fee; go-to APR = standard purchase APR |
| `CLB-PRD-CLI-PRESCREEN@v2` | 2026-01-05 → | prescreened firm CLI offers; displayed on desktop; valid-through date |
| `CLB-PRD-HRP@v3` | 2025-11-03 → | Hardship Relief Plan: reduced APR 9.9%, card restricted from new credit products for 6 months, flag `HARDSHIP_ACTIVE` |

## Incentives (`provenance: invented`)

| doc_id@version | effective | Content |
|---|---|---|
| `CLB-INC-2026-Q4@v1` | 2026-10-01 → 2026-12-31 | points per BT, CLI, add-on enrollment, Flex plan; §3.2 a product change on a close/fee call counts as a "save"; §5 incentive context is never evidence of individual misconduct |

## Skills (`data/corpus/skills/*.md`, front matter `name, description, routes, version`)

`add-on-consent`, `balance-transfer-disclosure`, `credit-line-increase`, `product-change`, `retention`, `hardship-and-vulnerability`, `scra`, `complaints`, `multilingual-review`, `memory-hygiene`, `automated-adjudication`.
