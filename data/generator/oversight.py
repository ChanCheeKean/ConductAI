"""Legacy scanner and reviewer baselines (historical labels only)."""
from __future__ import annotations

from common import AS_OF_ISO, Ctx, add_seconds, sub_rng
import records as R

RULES = [
    ("SCN-CONSENT-NEG-ENROLL","negative or minimal consent near enrollment"), ("SCN-OUTBOUND-SALE","sale on outbound call"),
    ("SCN-CREDIT-ASSURANCE","credit-impact assurance"), ("SCN-WAIVER-ENROLL-60S","waiver and enrollment proximity"),
    ("SCN-NO-FEE-DISCLOSED","fee disclosure absent"), ("SCN-NO-INTEREST-FRAMING","no-interest wording"),
    ("SCN-PREAPPROVED","pre-approved wording"), ("SCN-CLOSE-OBSTRUCTION","close request not completed"),
    ("SCN-COMPLAINT-NO-DISPOSITION","complaint phrase without disposition"), ("SCN-HARDSHIP-SALE","sale with hardship flag"),
    ("SCN-POSTCALL-ENROLL","enrollment after call end"), ("SCN-FAST-DISCLOSURE","disclosure over speed limit"),
    ("SCN-TOPDECILE-ADDON-TEAMFLAG","high add-on volume on team with finding"), ("SCN-RECORDING-GAP-SALE","sale overlaps recording gap"),
]


def build(ctx: Ctx):
    for n,(rid,desc) in enumerate(RULES):
        ctx.add("scanner_rules",dict(rule_id=rid,description=desc,rule_logic=f"deterministic_rule_{n+1}",
            glossary_version_basis="CLB-GLOSS@v8" if rid!="SCN-PREAPPROVED" else "CLB-GLOSS@v6",
            deployed_at="2026-11-01T05:00:00Z",available_at="2026-11-01T05:00:00Z",is_hero=False))
    rows=sorted((i for i in ctx.t["interactions"] if not i["is_hero"]),key=lambda x:x["interaction_id"])
    positives=[i for i in rows if ctx.bg_labels[i["interaction_id"]]["gold_status"]=="misconduct"]
    negatives=[i for i in rows if ctx.bg_labels[i["interaction_id"]]["gold_status"]=="no_error"]
    already={f["interaction_id"] for f in ctx.t["scanner_flags"] if not f["is_hero"]}
    target=round(len(rows)*.09)
    flagged=[]
    # Preserve scanner recall in every weekly slice instead of concentrating it
    # in opaque-ID order.
    by_week={}
    for inter in positives:
        key=inter["started_at_utc"][:10]
        by_week.setdefault(key,[]).append(inter)
    for key in sorted(by_week):
        flagged.extend(by_week[key][:round(len(by_week[key])*.70)])
    flagged.extend(negatives[:max(0,target-len(flagged))])
    for n,inter in enumerate(flagged):
        if inter["interaction_id"] in already: continue
        R.scanner_flag(ctx,inter,RULES[n%len(RULES)][0],add_seconds(inter["ended_at_utc"],300),matched_text="rules-engine match")
        if ctx.bg_labels[inter["interaction_id"]]["gold_status"]=="misconduct":
            R.scanner_flag(ctx,inter,RULES[(n+5)%len(RULES)][0],add_seconds(inter["ended_at_utc"],360),matched_text="second independent rule match")
    # Hero triggers enter the same scanner stream using their observable gold
    # category only while the evaluator dataset is being authored.
    already_all={f["interaction_id"] for f in ctx.t["scanner_flags"]}
    for inter in ctx.t["interactions"]:
        lab=ctx.bg_labels.get(inter["interaction_id"],{})
        if inter["is_hero"] and lab.get("gold_status")=="misconduct" and inter["interaction_id"] not in already_all:
            R.scanner_flag(ctx,inter,RULES[0][0],add_seconds(inter["ended_at_utc"],300),matched_text="hero trigger rule match")

    # Historical QA is confined to interactions completed by 2026-09-25 and
    # recorded before automated governance took effect on 2026-10-01.
    historical=[i for i in rows if i["ended_at_utc"][:10]<="2026-09-25"]
    hist_pos=[i for i in historical if ctx.bg_labels[i["interaction_id"]]["gold_status"]=="misconduct"]
    hist_neg=[i for i in historical if ctx.bg_labels[i["interaction_id"]]["gold_status"]=="no_error"]
    targets={"R-A":(.79,.76),"R-B":(.74,.71),"R-C":(.75,.77)}
    review_count=round(len(rows)*.16/3)
    baseline={}
    for reviewer,(precision_target,recall_target) in targets.items():
        tp_n=round(len(hist_pos)*recall_target); fp_n=round(tp_n*(1/precision_target-1))
        rr=sub_rng("reviewer",reviewer); pos=hist_pos[:]; neg=hist_neg[:]; rr.shuffle(pos); rr.shuffle(neg)
        selected_pos=pos[:tp_n]; selected_neg=neg[:fp_n]
        extras=[x for x in neg[fp_n:] if x not in selected_neg][:max(0,review_count-tp_n-fp_n)]
        for seq,(inter,verdict) in enumerate([(x,"misconduct") for x in selected_pos+selected_neg]+[(x,"no_error") for x in extras]):
            gt=ctx.bg_labels[inter["interaction_id"]]
            ctx.add("qa_reviews",dict(qa_review_id=f"QA-{reviewer[-1]}-{seq:05d}",interaction_id=inter["interaction_id"],
                reviewer_id=reviewer,reviewed_at="2026-09-30T23:00:00Z",selected_by="scanner" if seq<int(review_count*.7) else "random",
                verdict=verdict,category=(gt["gold_categories"][0] if verdict=="misconduct" and gt["gold_categories"] else "MC-03"),
                notes="legacy historical QA label",available_at="2026-09-30T23:00:00Z",is_hero=False))
        baseline[reviewer]={"tp":tp_n,"fp":fp_n,"fn":len(hist_pos)-tp_n,"tn":len(hist_neg)-fp_n,
                            "precision":round(tp_n/(tp_n+fp_n),4),"recall":round(tp_n/len(hist_pos),4)}
    ctx.reviewer_baseline={"gold_positive_count":len(hist_pos),"population":len(historical),"period_end":"2026-09-25",
                           "reviewers":baseline,
                           "note":"legacy reviewers before automated current-period governance"}
