"""Author ConductAI's deterministic, versioned policy corpus.

The text is deliberately concise: regulation documents are research-grounded
abridgements, while Copperlake documents are fictional governance artifacts.
Run from any directory with ``python3 data/corpus/author_corpus.py``.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def meta(doc_id: str, version: str, title: str, family: str, start: str, end: str = "", status: str = "active",
         supersedes: str = "", superseded_by: str = "", provenance: str = "invented", owner: str = "Copperlake Bank") -> dict:
    return {"doc_id": doc_id, "version": version, "title": title, "family": family,
            "effective_from": start, "effective_to": end, "status": status, "supersedes": supersedes,
            "superseded_by": superseded_by, "provenance": provenance, "owner": owner}


DOCS: list[tuple[dict, str]] = []


def add(m: dict, body: str) -> None:
    DOCS.append((m, body.strip() + "\n"))


def policy(m: dict, sections: list[tuple[str, str]]) -> None:
    add(m, "\n\n".join(f"## §{clause} {title}\n\n{text}" for clause, title, text in sections))


# Primary-law abridgements. These are summaries, not legal advice or complete text.
reg = "regulation"
add(meta("REG-UDAAP", "2010", "Consumer Financial Protection Act — UDAAP abridgement", reg, "2011-07-21",
         provenance="regulation_abridged", owner="United States Congress"), """
> Research abridgement for synthetic review. Consult the governing law for complete text.

## §1031(b) Deceptive conduct

The Bureau may act against an unfair, deceptive, or abusive act or practice involving a consumer-financial product or service. A representation or omission is assessed in context, including whether it is likely to mislead and material to a consumer.

## §1031(c) Unfair conduct

An act is unfair when it causes or is likely to cause substantial consumer injury that consumers cannot reasonably avoid and that is not outweighed by countervailing benefits.

## §1031(d) Abusive conduct

Abusive conduct materially interferes with understanding a term or condition, or takes unreasonable advantage of a consumer's lack of understanding, inability to protect their interests, or reasonable reliance.

## §1036 Prohibited acts

Covered persons and service providers may not commit or engage in unfair, deceptive, or abusive acts or practices.
""")
policy(meta("REGZ-1026.51", "2010", "Regulation Z §1026.51 abridgement", reg, "2010-02-22", provenance="regulation_abridged", owner="CFPB"), [
    ("1026.51(a)", "Ability to pay", "A card issuer must consider a consumer's ability to make required minimum payments before opening a credit-card account or increasing its credit limit.")])
policy(meta("REGZ-1026.9", "2010", "Regulation Z §1026.9 abridgement", reg, "2010-08-22", provenance="regulation_abridged", owner="CFPB"), [
    ("1026.9(c)", "Change-in-terms notice", "Certain significant changes require written notice at least 45 days before the change. This detail is marked unverified for the POC and is not load-bearing ground truth.")])
policy(meta("REGZ-1026.13", "2010", "Regulation Z §1026.13 abridgement", reg, "2010-02-22", provenance="regulation_abridged", owner="CFPB"), [
    ("1026.13", "Billing-error resolution", "A creditor must acknowledge and investigate a qualifying written billing-error notice within the regulation's deadlines and correct the account or explain its conclusion.")])
policy(meta("REGZ-1026.56", "2010", "Regulation Z §1026.56 abridgement", reg, "2010-02-22", provenance="regulation_abridged", owner="CFPB"), [
    ("1026.56", "Over-the-limit opt-in", "An issuer generally may not charge an over-the-limit fee unless the consumer affirmatively consents after receiving required disclosures.")])
policy(meta("REGZ-1026.52", "pre-2024", "Regulation Z §1026.52 penalty-fee abridgement", reg, "2010-08-22", provenance="regulation_abridged", owner="CFPB"), [
    ("1026.52(b)", "Penalty fees", "Penalty fees must be reasonable and proportional. Regulation Z provides inflation-indexed safe-harbor amounts; this abridgement intentionally asserts no current dollar amount.")])
policy(meta("REGZ-1026.52", "2024-03-15", "2024 late-fee amendment — vacated", reg, "2024-05-14", "2025-04-15", "vacated",
            provenance="regulation_abridged", owner="CFPB"), [
    ("1026.52(b)(1)(ii)(B)", "Vacated $8 safe harbor", "The 2024 rule created an $8 late-fee safe harbor for larger issuers. A court vacated the rule on 2025-04-15; it is not governing policy and the prior framework applies.")])
policy(meta("FCRA-INQUIRY", "2003", "FCRA inquiry mechanics abridgement", reg, "2003-12-04", provenance="paraphrase", owner="United States Congress"), [
    ("604", "Permissible purpose", "A consumer report may be obtained only for a permissible purpose authorized by the Fair Credit Reporting Act."),
    ("INQ-1", "Hard and soft inquiry mechanics", "Industry terminology distinguishes inquiries visible to other creditors from account-review or promotional inquiries. Exact scoring effects vary; colleagues must not promise a precise score outcome. This mechanics summary is marked unverified.")])
policy(meta("FCRA-PRESCREEN", "2003", "FCRA prescreen abridgement", reg, "2003-12-04", provenance="paraphrase", owner="United States Congress"), [
    ("604(c)", "Firm offers", "A consumer report may support a prescreened transaction when the creditor makes a firm offer of credit subject to permitted criteria."),
    ("615(d)", "Prescreen disclosure", "A prescreened solicitation must contain the applicable clear and conspicuous prescreen and opt-out disclosures. This is a POC paraphrase.")])
policy(meta("REGB-1002", "2011", "Regulation B abridgement", reg, "2011-12-30", provenance="regulation_abridged", owner="CFPB"), [
    ("1002.2(z)", "Prohibited basis", "Prohibited bases include race, color, religion, national origin, sex, marital status, and age when the applicant has capacity to contract, among other protected grounds."),
    ("1002.4(a)", "Discrimination prohibited", "A creditor may not discriminate against an applicant on a prohibited basis in any aspect of a credit transaction."),
    ("1002.9", "Adverse action", "Creditors must provide required notice of adverse action and its reasons or the right to request them.")])
policy(meta("SCRA-3937", "2003", "Servicemembers Civil Relief Act §3937 abridgement", reg, "2003-12-19", provenance="regulation_abridged", owner="United States Congress"), [
    ("3937(a)", "Six-percent maximum", "Interest on qualifying obligations incurred before military service, including credit-card debt, is limited to six percent during the covered period; excess interest is forgiven, not deferred."),
    ("3937(b)", "Notice and orders", "The servicemember supplies written notice and qualifying military orders or other appropriate evidence within the statutory period.")])
policy(meta("TSR-310", "2016", "Telemarketing Sales Rule abridgement", reg, "2016-06-13", provenance="regulation_abridged", owner="Federal Trade Commission"), [
    ("310.3(a)(1)", "Material disclosures", "Before a customer pays, a telemarketer must truthfully disclose required material information about the offered goods or services."),
    ("310.4(a)(7)", "Express informed consent", "A telemarketer must obtain the consumer's express informed consent to be charged using the payment method.")])

# Copperlake policies.
pol = "policies"
policy(meta("CLB-SOP-SAL-001", "v3", "Sales consent and disclosure", pol, "2025-01-06", "2026-05-31", "superseded", superseded_by="CLB-SOP-SAL-001@v4"), [
    ("3.1", "Affirmative consent", "Obtain a clear verbal yes to the specific named product after its price and material terms. Minimal assent to a statement or tag question is not consent."),
    ("3.2", "Terms before consent", "Give price and material terms before asking for consent."),
    ("4.1", "Enrollment timing", "Submit only during the interaction after consent."),
    ("5.3", "Clear delivery", "Required disclosures must be delivered clearly."),
    ("5.4", "Questions", "Answer price or term questions before enrollment."),
    ("6.1", "No bundling", "Never condition servicing or a fee waiver on a sale.")])
policy(meta("CLB-SOP-SAL-001", "v4", "Sales consent and disclosure", pol, "2026-06-01", supersedes="CLB-SOP-SAL-001@v3"), [
    ("3.1", "Affirmative consent", "Affirmative consent is a clear verbal yes to a specific named product after price and material terms. “Mm-hmm,” “uh-huh,” or “okay” responding to a statement or tag question is not affirmative consent."),
    ("3.2", "Terms before consent", "Disclose price and all material terms before asking for consent."),
    ("4.1", "Enrollment timing", "Submit enrollment during the interaction and after consent. An enrollment submitted after the interaction ends has no consent."),
    ("5.3", "Clear delivery", "Deliver required disclosures clearly. A required disclosure faster than 220 words per minute is not clear."),
    ("5.4", "Questions", "Answer every customer question about price or terms before enrollment."),
    ("6.1", "No bundling", "Do not condition or bundle a servicing request or fee waiver with a sale.")])
policy(meta("CLB-SOP-SAL-002", "v3", "Outbound-sales restrictions", pol, "2025-09-02"), [
    ("3.1", "Outbound servicing", "Do not sell on an outbound servicing call."),
    ("3.2", "Callback exception", "A sale is permitted only when the customer requested the callback, the request named the same product or offer, the call occurs within three business days, and consent to call was recorded.")])
policy(meta("CLB-SOP-SRV-002", "v2", "Courtesy fee waivers", pol, "2025-03-03"), [
    ("2.1", "Eligibility", "One courtesy late-fee waiver is available per rolling 12 months when none was granted in the prior 12 months."),
    ("3.1", "No conditioning", "A waiver is never conditional on a purchase or enrollment.")])
policy(meta("CLB-SOP-SRV-003", "v5", "Complaint handling", pol, "2026-02-02"), [
    ("2.1", "Definition", "A complaint is any expression of dissatisfaction about a product, service, fee, or colleague, whether or not the customer says “complaint.”"),
    ("3.1", "Logging", "Log the complaint in the same interaction with received_at equal to the expression time and disposition COMPLAINT."),
    ("3.2", "Acknowledgment", "Acknowledge within five business days."),
    ("3.3", "Underlying validity", "A valid underlying fee does not remove the duty to log dissatisfaction.")])
policy(meta("CLB-SOP-SRV-004", "v2", "Customer remediation matrix", pol, "2026-04-06"), [
    ("2.1", "Misrepresented fee", "Refund charged minus represented fee; for a balance transfer also offer cancellation with full fee refund within 30 days."),
    ("2.2", "Undisclosed product change", "After customer confirmation, reverse the change, restore rewards, and honor the represented outcome."),
    ("2.3", "Unconsented enrollment", "Reverse enrollment and refund premiums when consent is absent or unverifiable."),
    ("2.4", "Protected situation", "Reverse the plan or product and refund fees."),
    ("2.5", "Cancellation not honored", "Honor cancellation after confirmation and refund an annual fee inside the agreement window; do not claw back retention credits."),
    ("2.6", "Inquiry misinformation", "Send a correction letter; never request deletion of an authorized inquiry."),
    ("2.7", "Vulnerable-customer upgrade", "Reverse the upgrade, refund the annual fee, and send a support letter."),
    ("2.8", "Unlogged complaint", "Log it with the original received date."),
    ("2.9", "Solicitation after opt-out", "Suppress future solicitation. Keep an accepted product unless the customer asks to reverse."),
    ("2.10", "Customer choice", "When reversal could make the customer worse off, explain options and wait for the customer's choice.")])
policy(meta("CLB-SOP-VUL-001", "v2", "Hardship and vulnerability", pol, "2025-11-03"), [
    ("3.1", "Indicators", "Indicators are confusion about caller or purpose; third-party reliance; inability to restate terms; repeated deferential assent; disclosed job loss or reduced income; bereavement or serious illness."),
    ("3.2", "Two indicators", "With two or more indicator types, pause any sale and offer a callback or trusted-contact involvement."),
    ("4.1", "Active hardship", "Do not sell Flex Installments, balance transfers, credit-line increases, or upgrades during an active Hardship Relief Plan."),
    ("5.1", "Age excluded", "Age, birth year, and assumed age are never vulnerability indicators.")])
policy(meta("CLB-SOP-SCRA-001", "v3", "SCRA referral", pol, "2025-06-02"), [
    ("2.1", "Trigger", "Any mention of military orders, active duty, mobilization, or deployment triggers the process."),
    ("3.1", "Open review", "Open an SCRA benefits review in the same interaction."),
    ("3.2", "Explain scope", "Explain that the six-percent cap covers qualifying pre-service obligations, including credit cards."),
    ("4.1", "Eligibility", "The SCRA benefits team decides eligibility; the servicing colleague does not.")])
policy(meta("CLB-POL-CLI", "v5", "Credit-line increase policy", pol, "2024-02-01", "2026-09-30", "superseded", superseded_by="CLB-POL-CLI@v6"), [
    ("2.1", "Inquiry", "All customer-requested credit-line increases use a soft inquiry."),
    ("3.1", "Ability to pay", "Collect and evaluate income and obligations.")])
policy(meta("CLB-POL-CLI", "v6", "Credit-line increase policy", pol, "2026-10-01", supersedes="CLB-POL-CLI@v5"), [
    ("2.1", "Inquiry", "Use a soft inquiry unless account tenure is under 12 months or the requested increase exceeds $5,000; either exception requires a hard inquiry."),
    ("2.2", "Disclosure", "Tell the customer before submission whenever a hard inquiry applies."),
    ("3.1", "Ability to pay", "Collect and evaluate income and obligations."),
    ("9", "Change record", "CHC-CLI update: pending.")])
policy(meta("CLB-SOP-CRM-001", "v4", "Conduct-review selection", pol, "2025-03-03", "2026-08-31", "superseded", superseded_by="CLB-SOP-CRM-001@v5"), [
    ("3", "Selection", "Include a five-percent random slice."), ("4", "SLA", "Decide within 15 business days.")])
policy(meta("CLB-SOP-CRM-001", "v5", "Conduct-review selection", pol, "2026-09-01", supersedes="CLB-SOP-CRM-001@v4"), [
    ("3.1", "Capacity", "Apply weekly review capacity."),
    ("3.2", "Random slice", "Allocate 10% of capacity to a seeded, channel-stratified random slice using seed 20261116."),
    ("3.3", "Permitted signals", "Permitted signals: sale or enrollment, outbound sale, cancellation within 30 days, complaint within seven days, recording gap, protected-situation flag, scanner flag, and prior substantiated findings in 90 days."),
    ("3.4", "Prohibited selection features", "Never select using customer age, language, accent, ASR confidence, site, or colleague demographics."),
    ("4.1", "Decision SLA", "Decide within 10 business days after the later of interaction date and selection or trigger date. Exclude weekends and US bank holidays.")])
policy(meta("CLB-SOP-CRM-003", "v3", "Legacy conduct adjudication", pol, "2025-03-03", "2026-09-30", "superseded", superseded_by="CLB-SOP-CRM-003@v4"), [
    ("3", "Legacy approval", "Historical process: a human tester approved every adverse finding. This superseded process must never be used for current-period reviews.")])
policy(meta("CLB-SOP-CRM-003", "v4", "Automated conduct adjudication", pol, "2026-10-01", supersedes="CLB-SOP-CRM-003@v3"), [
    ("3.1", "Panel trigger A", "Trigger the automated panel when severity is high and any of these applies: remediation above $250, vulnerability or hardship, rights misinformation, colleague pattern, or systemic population of at least 10."),
    ("3.2", "Panel trigger B", "Also trigger when computed confidence in an adverse finding is at least 0.60 but below 0.85."),
    ("3.3", "Roles", "The panel has independent customer advocate and colleague advocate positions followed by an adjudicator."),
    ("4.1", "Computed confidence", "Compute confidence from verifier pass rate, citation verification, evidence coverage, decisive-span transcript quality, and panel agreement. Self-reported confidence never gates."),
    ("5.1", "Colleague threshold", "An adverse colleague finding requires computed confidence of at least 0.75. Below it, return no_adverse_finding; coaching or enhanced monitoring remains allowed."),
    ("5.2", "Customer default", "Remediate when harm is plausible at confidence 0.50 or greater, or consent is unverifiable."),
    ("5.3", "Systemic record", "A systemic finding requires a recorded population query."),
    ("6.1", "Allowed actions", "Allowed automated actions: refund or credit; reverse an enrollment, plan, or product change after required confirmation; restore rewards; log and acknowledge a complaint; suppress solicitation; open SCRA or specialist review; send approved letters; create coaching or enhanced-monitoring records; write governed memory."),
    ("7.1", "Forbidden actions", "Never take employment, disciplinary, or compensation action; initiate account closure; seek deletion of an authorized inquiry; contact regulators or third parties; or use a prohibited basis.")])
policy(meta("CLB-SOP-CRM-004", "v2", "Fair conduct monitoring", pol, "2026-01-05"), [
    ("2.1", "Customer features", "Do not use age, birth year, language, accent, national origin, ASR confidence as risk, or site."),
    ("2.2", "Colleague features", "Do not use demographics, site, or team membership as evidence against a colleague."),
    ("3.1", "Pattern boundary", "Never extend one colleague's pattern to teammates.")])
policy(meta("CLB-SOP-CRM-005", "v2", "Agent-memory governance", pol, "2026-01-05"), [
    ("2", "Lifecycle", "Memory-note states are active, superseded, retracted, archived, and purged."),
    ("3.1", "Supersede", "When a governing source changes, supersede the note and set valid_to."),
    ("3.2", "Retract", "Retract a note that was wrong from its creation."),
    ("4.1", "Colleague scope", "Colleague notes must be evidence-backed, time-bounded, and scoped to one colleague; do not import them to teammates."),
    ("5.1", "Purge", "Purge a note relying on a prohibited basis and retain a tombstone."),
    ("6.1", "Consolidate", "Consolidate raw observations into one validity-bounded note with sources.")])

# Glossary versions.
def glossary(version: str, start: str, end: str, status: str, preapproved: str, no_interest: str, supersedes="", superseded_by="") -> None:
    sections = []
    names = ["Unauthorized enrollment", "Consent failure", "Misrepresentation", "Disclosure failure", "Credit-reporting misinformation", "Coercion or obstruction", "Prohibited outbound sale", "Undisclosed product change", "Protected-situation sale", "Rights misinformation", "False records"]
    for i, name in enumerate(names, 1):
        sections.append((f"MC-{i:02d}", name, f"Category MC-{i:02d}: {name}. Review the full context, controlling policy, evidence quality, exceptions, and customer harm; classify bright-line violations separately from judgment calls."))
    sections += [
        ("MC-02.1", "Minimal assent", "A minimal response to a statement or tag question is not affirmative consent."),
        ("MC-02.2", "After-call submission", "An enrollment submitted outside the interaction lacks interaction consent."),
        ("MC-03.2", "Pre-approved language", preapproved),
        ("MC-03.3", "No-interest language", no_interest),
        ("MC-04.1", "Omitted disclosure", "Omission of a required disclosure is MC-04."),
        ("MC-04.2", "Unclear delivery", "Delivery above the SOP speed limit is MC-04."),
        ("MC-05.1", "Numeric predictions", "A specific claim such as “drop a hundred points” is MC-05."),
        ("MC-05.2", "Hard inquiry", "Describing a hard inquiry as having no credit impact is MC-05."),
        ("MC-06.1", "Conditioning", "Conditioning a waiver or servicing outcome on a sale is MC-06."),
        ("MC-06.2", "Cancellation", "Failure to process a clear cancellation request is MC-06."),
        ("MC-07.1", "Outbound", "A sale on an outbound call outside the callback exception is MC-07."),
        ("MC-08.1", "Product change", "Failure to disclose rewards, benefit, or fee consequences is MC-08."),
        ("MC-09.1", "Protected situation", "A sale during active hardship or after qualifying vulnerability indicators is MC-09."),
        ("MC-10.1", "Rights", "Misinformation about SCRA, complaint, or dispute rights is MC-10."),
        ("MC-10.2", "Complaint logging", "Failure to log a complaint is MC-10."),
        ("MC-11.1", "False record", "A CRM note or disposition contradicting the interaction is MC-11."),
        ("EX-1", "General credit factors", "A general statement that closing could affect utilization and account-history length is not MC-05.")]
    policy(meta("CLB-GLOSS", version, "Conduct misconduct glossary", "glossary", start, end, status,
                supersedes=supersedes, superseded_by=superseded_by), sections)


glossary("v6", "2025-07-01", "2026-06-30", "superseded", "Any colleague use of “pre-approved” or “pre-qualified” is MC-03.", "No-interest framing is permitted when the fee is disclosed in the same turn.", superseded_by="CLB-GLOSS@v7")
glossary("v7", "2026-07-01", "2026-10-31", "superseded", "“Pre-approved” is permitted only when a valid prescreened firm offer is displayed on the colleague desktop; otherwise it is MC-03.", "No-interest framing is permitted when the fee is disclosed in the same turn.", supersedes="CLB-GLOSS@v6", superseded_by="CLB-GLOSS@v8")
glossary("v8", "2026-11-01", "", "active", "“Pre-approved” is permitted only when a valid prescreened firm offer is displayed on the colleague desktop; otherwise it is MC-03.", "Describing a fee-based plan as “no interest” or “interest-free” is prohibited even when the fee is disclosed.", supersedes="CLB-GLOSS@v7")

# Handling cards, products, and incentives.
scripts = "scripts"
policy(meta("CLB-CHC-CLI", "v3", "CLI handling card", scripts, "2024-02-01", "2026-03-01", "superseded", superseded_by="CLB-CHC-CLI@v4"), [("2.1", "Inquiry statement", "This request will not impact your credit score.")])
policy(meta("CLB-CHC-CLI", "v4", "CLI handling card", scripts, "2026-03-02", supersedes="CLB-CHC-CLI@v3"), [("2.1", "Inquiry statement", "This request will not impact your credit score."), ("2.2", "Ability to pay", "Ask about income and obligations before submission.")])
policy(meta("CLB-CHC-BT", "v4", "Balance-transfer handling card", scripts, "2025-05-05", "2026-10-14", "superseded", superseded_by="CLB-CHC-BT@v5"), [("2.1", "Rates", "State promotional APR, promotional duration, and go-to APR."), ("2.2", "Fee", "State the transfer fee percentage.")])
policy(meta("CLB-CHC-BT", "v5", "Balance-transfer handling card", scripts, "2026-10-15", supersedes="CLB-CHC-BT@v4"), [("2.1", "Rates", "State promotional APR, promotional duration, and go-to APR."), ("2.2", "Fee", "State both the fee percentage and dollar amount for the requested transfer.")])
policy(meta("CLB-CHC-PC", "v3", "Product-change handling card", scripts, "2025-08-04"), [("2.1", "Rewards", "Disclose the conversion rate and resulting rewards value."), ("2.2", "Benefits", "Disclose benefits removed, including trip protection when applicable."), ("2.3", "Consent", "Obtain explicit consent to the named product change.")])
policy(meta("CLB-CHC-ADDON-CS", "v3", "CardShield handling card", scripts, "2025-10-06"), [("2.1", "Price", "Say exactly: “eighty-nine cents for every hundred dollars of your ending statement balance, and you can cancel anytime”."), ("2.2", "Consent", "Ask “Would you like me to add CardShield?” and wait for a clear yes.")])
policy(meta("CLB-CHC-ADDON-CW", "v2", "CreditWatch handling card", scripts, "2025-10-06"), [("2.1", "Price", "CreditWatch Plus is $14.99 a month and you can cancel anytime."), ("2.2", "Consent", "Ask for the named product and wait for a clear yes.")])
policy(meta("CLB-CHC-FLEX", "v2", "Flex handling card", scripts, "2026-04-06"), [("2.1", "Fee", "State the fixed monthly plan fee as both a percentage and dollar amount."), ("2.2", "Framing", "Do not describe the plan as no interest.")])
policy(meta("CLB-CHC-FLEX-ES", "v2", "Tarjeta de manejo Flex", scripts, "2026-04-06"), [("2.1", "Cargo", "Indique el cargo mensual fijo como porcentaje y como monto en dólares."), ("2.2", "Descripción", "No describa el plan como sin intereses.")])
policy(meta("CLB-CHC-RET", "v2", "Retention handling card", scripts, "2025-08-04"), [("2.1", "Close request", "Process closure no later than the customer's second clear request."), ("2.2", "Offer limit", "Make at most one retention offer."), ("2.3", "Credit statements", "Do not predict a score; discuss only general credit factors.")])

products = "products"
policy(meta("CLB-PRD-CARDHOLDER-AGREEMENT", "v9", "Cardholder agreement", products, "2025-01-06"), [("4.2", "Late fee", "A late fee may be charged up to $32."), ("4.3", "Returned payment", "The returned-payment fee is $29."), ("6.1", "Annual-fee refund", "Refund the annual fee in full when the account closes within 30 days of its posting."), ("7.1", "Product changes", "Convert rewards at the applicable product fact-sheet conversion rate.")])
policy(meta("CLB-PRD-EVERYDAY-CASH", "v4", "Everyday Cash fact sheet", products, "2025-01-06"), [("1", "Terms", "No annual fee; 1.5% cash back; no trip protection.")])
policy(meta("CLB-PRD-VOYAGER", "v5", "Voyager fact sheet", products, "2025-01-06"), [("1", "Annual fee", "$95 annual fee and miles rewards."), ("3", "Trip protection", "Trip protection applies to eligible travel bought with the card."), ("5", "Conversion", "A change to a cash-back card converts miles at 0.5 cents per mile.")])
policy(meta("CLB-PRD-SUMMIT", "v3", "Summit fact sheet", products, "2025-01-06"), [("1", "Annual fee", "$450 annual fee, billed on upgrade.")])
policy(meta("CLB-PRD-FOUNDATION", "v2", "Foundation fact sheet", products, "2025-01-06"), [("1", "Product", "Foundation is a secured credit card.")])
policy(meta("CLB-PRD-CARDSHIELD", "v3", "CardShield fact sheet", products, "2025-10-06"), [("2.1", "Premium", "$0.89 per $100 of ending statement balance each month."), ("2.2", "When charged", "Charge whenever ending balance exceeds zero, including when the customer later pays in full."), ("3", "Cancellation", "Cancel anytime; no premium after cancellation.")])
policy(meta("CLB-PRD-CREDITWATCH", "v2", "CreditWatch Plus fact sheet", products, "2025-10-06"), [("2.1", "Price", "$14.99 monthly; the first fee bills on enrollment.")])
policy(meta("CLB-PRD-FLEX", "v2", "Flex Installments fact sheet", products, "2026-04-06"), [("2.1", "Plan fee", "A 12-month plan charges a fixed monthly fee of 1.72% of principal instead of interest."), ("2.2", "Rounding", "Round the fee to the nearest cent.")])
policy(meta("CLB-PRD-BT-OFFERS", "v6", "Balance-transfer offers", products, "2026-09-01"), [("OFR-BT-12-3", "12-month offer", "0% for 12 months with a 3% transfer fee."), ("OFR-BT-15-3", "Promotional segment", "0% for 15 months with a 3% fee; eligible promotional segment only."), ("OFR-BT-15-5", "15-month offer", "0% for 15 months with a 5% fee. Go-to APR equals the standard purchase APR.")])
policy(meta("CLB-PRD-CLI-PRESCREEN", "v2", "CLI prescreen offers", products, "2026-01-05"), [("1", "Firm offers", "A prescreened firm CLI offer must be displayed on desktop and used no later than its valid-through date.")])
policy(meta("CLB-PRD-HRP", "v3", "Hardship Relief Plan", products, "2025-11-03"), [("1", "Terms", "The plan reduces APR to 9.9%, restricts new credit products for six months, and sets HARDSHIP_ACTIVE.")])
policy(meta("CLB-INC-2026-Q4", "v1", "2026 Q4 incentive plan", "incentives", "2026-10-01", "2026-12-31"), [("2", "Points", "Points may be earned for balance transfers, credit-line increases, add-on enrollments, and Flex plans."), ("3.2", "Saves", "A product change on a close or annual-fee call counts as a save."), ("5", "Evidence boundary", "Incentive context is never evidence of individual misconduct.")])


SKILLS = {
    "add-on-consent": ("Review add-on consent and enrollment timing", ["Verify price and material terms preceded the ask.", "Treat minimal assent to a statement or tag question as no consent.", "Compare enrollment submission to interaction end; calculate premiums and remediation."]),
    "balance-transfer-disclosure": ("Review balance-transfer offer and fee disclosure", ["Join the presented and submitted offer records.", "Apply the handling-card version effective on the interaction date.", "Compute the transfer fee independently from amount and rate."]),
    "credit-line-increase": ("Review CLI inquiry disclosure and ability to pay", ["Resolve policy by interaction date.", "Compute tenure and requested increase thresholds.", "Distinguish an authorized inquiry from misinformation about its effect."]),
    "product-change": ("Review product-change disclosure and consent", ["Reconstruct rewards conversion, lost benefits, and annual-fee effect.", "Use desktop events to distinguish discussion from submission.", "Offer customer choice before a reversal that could worsen the outcome."]),
    "retention": ("Review retention and account-closure handling", ["Count clear closure requests.", "Allow no more than one retention offer.", "Separate general credit factors from numeric score predictions."]),
    "hardship-and-vulnerability": ("Review hardship flags and behavioral vulnerability", ["Check account flags and prior interactions.", "Count only policy-defined behavioral indicators; never age.", "Pause sales after two indicators and prohibit credit-product sales during active hardship."]),
    "scra": ("Review SCRA trigger and referral handling", ["Treat any military-orders or deployment mention as a trigger.", "Verify same-interaction referral.", "Do not let a servicing colleague decide eligibility."]),
    "complaints": ("Review complaint identification and logging", ["Recognize dissatisfaction without requiring the word complaint.", "Preserve the original received time.", "Do not excuse non-logging because the underlying fee was valid."]),
    "multilingual-review": ("Review multilingual interactions safely", ["Route Spanish or code-switched evidence to the correct transcript model.", "Treat language, accent, and ASR confidence as quality signals only, never risk.", "Verify decisive phrases against word timings or re-transcription."]),
    "memory-hygiene": ("Apply governed memory read and write paths", ["Check validity, scope, source, and governing-version dates before use.", "Supersede changed guidance; retract originally false notes; purge prohibited-basis notes with tombstones.", "Never extend a colleague note to teammates."]),
    "automated-adjudication": ("Apply fully automated governance", ["Compute confidence from verifiable components.", "Invoke the automated panel only under the two trigger rules.", "Apply asymmetric defaults: plausible harm favors remediation; sub-threshold colleague evidence means no adverse finding."])
}


def render_front_matter(m: dict) -> str:
    lines = ["---"] + [f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in m.items()] + ["---", ""]
    return "\n".join(lines)


def write() -> None:
    for family in ("regulation", "policies", "glossary", "scripts", "products", "incentives", "skills"):
        target = ROOT / family
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
    index = []
    for m, body in sorted(DOCS, key=lambda x: (x[0]["family"], x[0]["doc_id"], x[0]["version"])):
        rel = Path(m["family"]) / f'{m["doc_id"]}@{m["version"]}.md'
        (ROOT / rel).write_text(render_front_matter(m) + f'# {m["title"]}\n\n' + body, encoding="utf-8")
        index.append({**m, "path": rel.as_posix()})
    for name, (description, steps) in sorted(SKILLS.items()):
        sm = {"name": name, "description": description, "routes": [name], "version": "1.0"}
        text = render_front_matter(sm) + f"# {description}\n\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)) + "\n"
        (ROOT / "skills" / f"{name}.md").write_text(text, encoding="utf-8")
    (ROOT / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Authored {len(index)} versioned documents and {len(SKILLS)} skills")


if __name__ == "__main__":
    write()
