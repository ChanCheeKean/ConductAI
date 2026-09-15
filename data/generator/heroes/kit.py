"""Helpers for hero case builders: ground truth, gold labels, personas.

Record constructors live in `records.py`; transcripts in `transcripts.py`; arithmetic in `derived.py`.
"""
from __future__ import annotations

from typing import Optional

from common import AS_OF_ISO, Ctx

GROUND_TRUTH_KEYS = (
    "review_id", "code", "title", "depth", "as_of", "interaction_ids", "summary", "trigger", "sla", "expected",
    "key_facts", "hypotheses", "contradictions", "pivots", "computations", "must_cite", "must_not", "memory_ops",
    "precedents", "acceptable_alternatives", "deterministic_checks", "rubric", "budget", "waits",
)
CHECK_OPS = {"eq", "approx", "in", "contains", "contains_text", "not_contains", "not_contains_any", "set_eq", "gte", "lte"}


def truth(ctx: Ctx, review_id: str, code: str, title: str, depth: str, **kw) -> dict:
    """Register a hero ground-truth file (data dictionary §10). Unknown keys raise; missing keys get empty defaults."""
    unknown = set(kw) - set(GROUND_TRUTH_KEYS)
    if unknown:
        raise KeyError(f"{code}: unknown ground-truth keys {sorted(unknown)}")
    gt = dict(review_id=review_id, code=code, title=title, depth=depth, as_of=AS_OF_ISO, schema_version="1.0")
    for k in GROUND_TRUTH_KEYS[5:]:
        gt[k] = kw.get(k, {} if k in ("trigger", "sla", "expected", "memory_ops", "precedents", "budget") else [])
    for chk in gt["deterministic_checks"]:
        if set(chk) != {"path", "op", "value"} or chk["op"] not in CHECK_OPS:
            raise ValueError(f"{code}: bad deterministic check {chk}")
    ctx.ground_truth[review_id] = gt
    return gt


def label(ctx: Ctx, interaction_id: str, gold_status: str, categories: Optional[list] = None, *,
          attributable_to: str = "none", customer_harm: bool = False, is_bright_line: Optional[bool] = None,
          source: str = "hero"):
    """Gold label for background_labels.jsonl. gold_status: no_error | misconduct | control_gap | insufficient_evidence."""
    ctx.bg_labels[interaction_id] = dict(
        interaction_id=interaction_id, gold_status=gold_status, gold_categories=categories or [],
        attributable_to=attributable_to, customer_harm=customer_harm, is_bright_line=is_bright_line, source=source)


def persona(ctx: Ctx, customer_id: str, review_id: str, *, disposition: str, reply_text: str, available_at: str,
            knows: list, disclosure_rules: list, style: str = "plain, cooperative"):
    """Simulated customer for outreach replies (harness only)."""
    ctx.personas[customer_id] = dict(
        customer_id=customer_id, review_id=review_id, disposition=disposition, style=style, facts_known=knows,
        disclosure_rules=disclosure_rules, reply_to_outreach=dict(template=reply_text, available_at=available_at))


def check(path: str, op: str, value) -> dict:
    return dict(path=path, op=op, value=value)
