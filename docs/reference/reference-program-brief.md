# GS Call Monitoring - Misconduct Detection Project

## 1. Executive Summary

The **GS Call Monitoring - Misconduct Detection** initiative is a GenAI-assisted call-monitoring solution for detecting potential sales misconduct in servicing interactions. The initial scope is **US phone servicing**. The solution is intended to support, not replace, the GS Conduct Risk Monitoring Program and its human testers.

The core idea is to make AI review calls using a set of evidence and rules that mirrors the existing human review process as closely as possible. The AI analyzes call transcripts together with structured call data and reference materials such as the Misconduct Glossary, policies, sales instructions, and product disclosures. It produces a potential-misconduct assessment, a reason, and a confidence indication. Human testers then validate the result.

The project is already in a pilot phase for US Front-Office Servicing (Phone), with a roadmap toward broader phone scale, chat, international English servicing, and eventually international non-English servicing.

---

## 2. The Problem the Project Is Solving

### Business problem

Sales and servicing conversations must be monitored for behavior that may violate conduct requirements, product rules, disclosures, or customer-treatment expectations. Today, misconduct assessment depends heavily on human review. Human reviewers have to combine multiple sources of evidence, including call recordings, screen activity, conduct guidance, policies, sales instructions, and product disclosures.

This creates a difficult monitoring problem: only a fraction of calls can be manually reviewed, while misconduct is relatively rare. The presentation reports an approximate **3.6% misconduct rate**, creating a severe class imbalance. A system that simply predicts the majority class (no misconduct) could appear accurate while missing the events that matter.

### Why automation is difficult

The PDF identifies four major technical/data challenges:

1. **Severe class imbalance** - misconduct is only about 3.6% of calls, so a model can become biased toward predicting non-misconduct.
2. **Human-vs-AI environment mismatch** - human reviewers can use call audio and screen recordings, whereas the model may depend on poor-quality transcripts and insufficient metadata.
3. **Label scarcity, sampling bias, and subjective labels** - only some calls are reviewed; non-random sampling can make labeled data unrepresentative. Human judgments also vary by experience, policy interpretation, fatigue, and borderline-case interpretation, which introduces noise into the ground truth.
4. **Concept drift and evolving guidelines** - misconduct language/techniques and internal guidelines change over time, and guideline changes without versioning make consistent model behavior harder.

### Practical problem statement

> **How can GS increase the efficiency and coverage of conduct-risk call monitoring by using GenAI to identify potential sales misconduct, while preserving human validation and dealing with incomplete context, rare positive cases, subjective labels, transcript quality, and evolving rules?**

---

## 3. Project Objective

The stated objective is to implement a **GenAI-powered solution that supports the GS Conduct Risk Monitoring Program by assisting GS Conduct Risk Testers in performing call monitoring more efficiently**.

The solution should:

- Detect **potential sales misconduct** in US servicing calls.
- Use **GPT-5+ LLMs** to analyze call transcripts.
- Combine transcripts with **structured data** and predefined guidance/reference information.
- Use materials such as the **Conduct Risk Misconduct Glossary** as part of the assessment.
- Generate results that remain subject to **two levels of human tester review** for validation and confirmation.

This means the AI is best understood as a **detection and decision-support layer**, not the final misconduct adjudicator.

---

## 4. What Success Looks Like

The pilot-launch material describes four intended outcomes:

- **Detect** - identify potential misconduct with high accuracy.
- **Understand** - use GenAI to comprehend conversations in context.
- **Protect** - safeguard customers and the business through proactive monitoring.
- **Improve** - drive better behaviors and strengthen sales integrity.

Operationally, success means increasing the ability to surface risky calls for review without creating an unmanageable number of false positives, while retaining enough recall to avoid missing misconduct.

---

## 5. Human Review Process

The human misconduct reviewer uses six major categories of information:

### 5.1 Call Records
Audio recordings of sales conversations are reviewed verbatim for misleading statements, pressure tactics, and omissions.

### 5.2 Screen Recordings
Agent desktop activity is cross-checked against the call audio, including to identify undisclosed product switching.

### 5.3 Misconduct Glossary
A firm-approved reference containing banned phrases, red-flag language, and known mis-selling patterns.

### 5.4 Policy & Procedures
Internal conduct rules, regulatory obligations, and escalation protocols governing sales activity.

### 5.5 Sales Instructions
Sales-process guidelines and instructions, including CHC.

### 5.6 Product Descriptions & Disclosures
Official product fact sheets and disclosures used to verify whether an agent's statements are accurate and complete.

### Human review output

The human review ultimately results in either:

- **No Errors**, or
- a **Misconduct Category**.

---

## 6. How the AI Mimics Human Review

The AI design intentionally maps to the same six broad information categories used by humans, but some inputs are represented differently.

| Human review input | AI review equivalent |
|---|---|
| Call audio / call records | Call transcripts |
| Screen recordings | Structured data / available contextual data |
| Misconduct Glossary | Misconduct Glossary |
| Policy & Procedures | Policy & Procedures |
| Sales Instructions | Sales Instructions |
| Product Descriptions & Disclosures | Product Descriptions & Disclosures |

The important limitation is that the AI does **not necessarily receive the same rich environment as a human reviewer**. The presentation explicitly calls out the mismatch between humans having audio/screen context and models operating with transcript quality and metadata limitations.

### AI review output

The AI produces either:

- **No Errors**, or
- **Potential Misconduct**.

The use of *potential* is important: the AI result is subsequently reviewed by human testers.

---

## 7. Data Inputs

The high-level workflow groups inputs into three types.

### 7.1 Sales Call Transcripts
Text representation of the servicing/sales conversation.

### 7.2 Unstructured Data
Examples shown in the presentation include:

- Misconduct Glossary
- Manuals, such as CHC
- Offer disclosures

### 7.3 Structured Call Data
Examples shown include:

- IVR flag
- Outbound-call indicator
- Offer acceptance

Different misconduct types require different combinations of these inputs.

---

## 8. Examples of Misconduct Detection

### Example 1 - Transcript only

**Misconduct:** The customer declined an offer and the colleague used excessive rebuttals.

**Example behavior:** CCP continues pitching after the Card Member declines twice.

This can be detected primarily from conversational content in the transcript.

### Example 2 - Structured data only

**Misconduct:** CCP processed a sale on an outbound call.

**Example behavior:** CCP initiates an outbound call to resume a sale/servicing request and completes a product offer.

This depends on structured context such as the inbound/outbound flag rather than language alone.

### Example 3 - Transcript + structured + unstructured data

**Misconduct:** Material/significant components of a product-offer disclosure were excluded.

**Example behavior:** Failure to read rate and fees at least once.

This requires joining what was said in the transcript with processed-offer information and the applicable offer disclosure.

These examples show that misconduct detection is not simply text classification. Some cases require **cross-source reasoning** over the conversation, transaction/call metadata, and policy or disclosure documents.

---

## 9. High-Level Technical Workflow

The workflow shown in the presentation is:

```text
Sales Call Transcripts
        +
Unstructured Reference Data
(Misconduct Glossary, manuals/CHC, offer disclosures)
        +
Structured Call Data
(IVR flag, outbound call, offer acceptance)
        |
        v
AI Misconduct Detection
        |
        +--> Detection Pipeline
        |      1. Input Normalization
        |      2. Classification
        |      3. Aggregation
        |      4. Validation
        |
        +--> EAG -> AI Firewall -> LLM
        |
        v
AI Detection Outcome
  - Classification
  - Reason
  - Confidence
        |
        v
1st Tester
  - No Error / Misconduct
        |
        v
2nd Tester
```

### Interpretation

The system first normalizes the available evidence, performs classification, aggregates results, and validates the output. The LLM is accessed through the illustrated EAG / AI Firewall path. The AI result contains a classification, rationale/reason, and confidence information. Human testing remains downstream of the model.

---

## 10. Human-in-the-Loop Control

The presentation explicitly states that generated results are reviewed by **two levels of testers**.

This is a central project-control principle:

```text
AI identifies potential misconduct
          |
          v
First human tester validates the case
          |
          v
Second human tester provides the next review level
```

Therefore, the model is not positioned as an autonomous enforcement mechanism. It is intended to improve the monitoring workflow while humans validate and confirm misconduct.

---

## 11. Model Performance

For transcripts with in-scope structured data, the presentation compares three human reviewers with the Misconduct AI.

| Reviewer / Model | Precision | Recall | FP Rate |
|---|---:|---:|---:|
| Reviewer A | 79% | 76% | 8.2% |
| Reviewer B | 74% | 71% | 9.8% |
| Reviewer C | 75% | 77% | 10.3% |
| Misconduct AI | 65% | 78% | 17.7% |

### What this means

The AI has **78% recall**, slightly higher than the human-reviewer values shown (71%-77%). In this dataset, it therefore identifies a relatively high proportion of actual misconduct cases.

However, its **65% precision** is below the human reviewers' 74%-79%, and its **17.7% false-positive rate** is materially higher than the human reviewers' 8.2%-10.3%.

The practical trade-off is therefore:

> The AI appears oriented toward catching more potential misconduct, but it generates more false alarms that humans must review.

The presentation notes that adding in-scope structured data can improve recall by reducing false negatives. It also states that some false positives remain because of subjective subcategories and low-quality transcripts, and that **majority voting** is used to mitigate this issue.

### Highlighted error categories

The slides call out examples including:

- Inaccurate information related to credit reporting, impact, or inquiry.
- Enrolling a customer in a product offer without consent.
- Leveraging the ability to cancel or return to an existing product to secure a sale.

---

## 12. Core Technical / ML Challenges

### 12.1 Rare-event detection

At ~3.6% prevalence, misconduct is a rare positive class. Accuracy by itself is therefore a poor metric. Recall, precision, false-positive rate, and false-negative behavior matter more.

### 12.2 Missing context

Humans may inspect audio and screen recordings. AI primarily receives transcripts and available structured/unstructured data. Any information lost during transcription or not represented in metadata can limit detection.

### 12.3 Transcript quality

Low-quality transcripts can alter meaning, omit words, or reduce the evidence needed to make a conduct judgment. The presentation directly connects transcript quality to false positives.

### 12.4 Ground-truth quality

Labels originate from human review and therefore inherit reviewer disagreement and subjectivity. This means the model may be trained/evaluated against a ground truth that itself contains uncertainty.

### 12.5 Sampling bias

If reviewed calls are selected by scanners or other non-random mechanisms, labeled data may not represent the full call population. A model trained on this sample can develop systematic blind spots.

### 12.6 Policy evolution / concept drift

Both misconduct techniques and governing guidelines change. The solution therefore needs a way to keep its reference knowledge and decision criteria aligned with current guidance.

---

## 13. Collaboration / Ownership Structure

The presentation describes misconduct detection as a cross-functional effort involving four groups:

- **ETS - EDAI:** AI/ML implementation.
- **GS - Control Management:** strategic coordination.
- **GS - Data Science:** data analytics.
- **GS - CVP:** Offer API enhancement.

The slide lists individual contributors under each pillar, emphasizing that the project requires coordination across AI engineering, controls, data science, and servicing/product-data capabilities.

---

## 14. Development Roadmap

The roadmap spans Q1 2026 through 2027+.

### US Front-Office Servicing - Phone

- Q1 2026: POC
- Q2 2026: Development
- Q3 2026: Pilot
- Q4 2026 onward: Full Scale

### US Front-Office Servicing - Chat

- Development begins around Q3 2026.
- Full-scale rollout follows from approximately Q4 2026 onward.

### International English Front-Office Servicing

- Development begins around Q4 2026.
- Pilot follows around 2027.
- Full scale follows after the pilot.

### International Non-English Front-Office Servicing

- Development is shown beginning in 2027+.

The overall expansion strategy is therefore approximately:

```text
US Phone -> US Chat -> International English -> International Non-English
```

---

## 15. Pilot Status / Context

The presentation announces the **Servicing Sales Misconduct Detection Pilot for Phone Channels**, powered by Generative AI. The launch messaging describes the solution as helping detect misconduct early, improve integrity, protect customers/business, and strengthen sales behavior.

The presentation's agenda covers pilot launch, objective, human review, AI review, model performance against a human baseline, and roadmap.

---

## 16. The Project in One End-to-End Story

A servicing call occurs. The organization has to determine whether the colleague's behavior contains a conduct issue. A human can make that judgment by listening to the call, reviewing screen activity, checking policies and instructions, and comparing statements against product disclosures. Doing this manually at scale is difficult, and only a subset of calls can be reviewed.

The project introduces a GenAI misconduct-detection layer. It gathers the call transcript, structured call attributes, and relevant reference materials. The detection pipeline normalizes those inputs, evaluates possible misconduct, aggregates/validates the results, and returns a classification, reason, and confidence.

The AI result is a **potential misconduct signal**, not a final decision. Human testers review the generated result, with two levels of tester validation in the stated design.

The biggest modeling challenge is balancing detection coverage against false alarms. The presented AI result has recall comparable to or slightly above the human reviewers shown, but lower precision and a higher false-positive rate. Structured data helps reduce false negatives, while subjective categories and transcript quality remain sources of false positives.

The longer-term goal is to scale the capability from the US phone pilot to broader phone coverage, chat, international English, and eventually non-English servicing.

---

## 17. Key Takeaways for Someone Joining the Project

1. **This is not just an LLM prompt-classification problem.** Correct detection can require transcripts, structured call/offer data, and policy/disclosure documents together.
2. **The AI is assisting a control process.** Human validation is part of the designed workflow.
3. **Recall is especially important because missing misconduct is costly, but false positives create reviewer workload.** The current results show this trade-off clearly.
4. **Data quality may be as important as model capability.** Transcript quality, missing metadata, biased samples, subjective labels, and guideline versioning all constrain performance.
5. **The human-review process is the design template.** The AI attempts to reproduce the six evidence categories used by misconduct reviewers, within the limits of available machine-readable data.
6. **Structured data materially matters.** Several misconduct scenarios cannot be determined from conversation text alone.
7. **The system must evolve with policy and behavior.** Concept drift and changing guidelines are explicit project risks.
8. **The current phone pilot is one stage of a broader roadmap.** The intended trajectory expands across channels, markets, and languages.

---

## 18. Questions the PDF Does Not Fully Answer

These are useful questions to clarify with the project team because the presentation does not provide enough detail to answer them conclusively:

- What exact misconduct taxonomy/subcategories are in scope for the current pilot?
- How are confidence scores calculated and how are thresholds selected?
- How exactly is majority voting implemented (multiple prompts, multiple model calls, multiple models, or another mechanism)?
- What GPT-5+ model/configuration is used in production and what evaluation controls surround model changes?
- What is the precise role of EAG and the AI Firewall in request/response processing?
- How are relevant policy, CHC, glossary, and disclosure documents selected for each call?
- Are these documents injected directly into prompts, retrieved dynamically, or processed through another knowledge/retrieval layer?
- How are guideline versions tracked so historical calls are evaluated against the correct policy version?
- How is transcript quality measured and what happens when transcript quality is insufficient?
- Which structured fields are currently available beyond IVR flag, outbound call, offer acceptance, and processed offers?
- How are reviewer disagreements resolved and how is the final ground-truth label constructed?
- What is the target operating point for precision, recall, and false-positive rate before full-scale rollout?
- What reviewer-workload reduction or monitoring-coverage improvement defines business success?
- How are pilot findings fed back into prompts, reference data, model evaluation, and tester procedures?

---

## 19. Concise Problem and Objective

### Problem

Manual misconduct monitoring cannot efficiently cover the full servicing-call population, while automated detection is difficult because misconduct is rare, relevant evidence spans multiple data sources, transcripts can be poor quality, labels are scarce/subjective, and conduct guidance changes over time.

### Objective

Build a GenAI-assisted misconduct detection system that analyzes servicing-call transcripts together with structured data and conduct/product guidance to identify **potential** sales misconduct efficiently, explain the detection, and route the result through two levels of human validation - initially for US phone servicing and later across additional channels and markets.

---

## Source

This document is derived from the 13-page presentation **"Call Monitoring - Misconduct Detection Model" / "2026-07_07_Biweekly_Update_GS_Call Monitoring Overview"**. Interpretive statements in this Markdown file are explicitly framed as summaries or implications of the presentation; unanswered implementation details are kept as open questions rather than filled in from outside knowledge.
