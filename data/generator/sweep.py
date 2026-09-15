"""Q01 weekly portfolio-selection ground truth."""
from __future__ import annotations

import random
from common import Ctx, SEED

FORCED=["INT-9000101","INT-9000801","INT-9000901","INT-9001401","INT-9001901","INT-9002101","INT-9002201","INT-9002301"]


def build(ctx: Ctx):
    week=[i for i in ctx.t["interactions"] if "2026-11-09"<=i["started_at_utc"][:10]<="2026-11-14"]
    flag_counts={}
    for x in ctx.t["scanner_flags"]: flag_counts[x["interaction_id"]]=flag_counts.get(x["interaction_id"],0)+1
    enroll={x["source_interaction_id"] for x in ctx.t["enrollments"]}|{x["interaction_id"] for x in ctx.t["offers"]}
    def score(i):
        return 10*(i["interaction_id"] in FORCED)+4*flag_counts.get(i["interaction_id"],0)+3*(i["interaction_id"] in enroll)+2*(i["recording_status"]=="partial")+1*(i["direction"]=="outbound")
    ranked=sorted(week,key=lambda i:(-score(i),i["interaction_id"]))
    picks=[]
    for iid in FORCED:
        if any(i["interaction_id"]==iid for i in week): picks.append(iid)
    for i in ranked:
        if i["interaction_id"] not in picks and len(picks)<36:picks.append(i["interaction_id"])
    random_picks=[]; rng=random.Random(SEED)
    for channel in ("phone","chat","secure_message"):
        pool=sorted(i["interaction_id"] for i in week if i["channel"]==channel and i["interaction_id"] not in picks)
        if pool: random_picks.append(rng.choice(pool))
    pool=sorted(i["interaction_id"] for i in week if i["interaction_id"] not in picks+random_picks)
    if pool: random_picks.append(rng.choice(pool))
    gold=sorted(i["interaction_id"] for i in week if ctx.bg_labels.get(i["interaction_id"],{}).get("gold_status")=="misconduct")
    risk_gold=sorted(set(picks)&set(gold)); recall=round(len(risk_gold)/len(gold),4) if gold else 1
    ctx.q01={"code":"Q01","as_of":"2026-11-16T15:00:00Z","week_start":"2026-11-09","week_end":"2026-11-13",
             "capacity":40,"risk_capacity":36,"random_capacity":4,"seed":SEED,"population_count":len(week),
             "gold_positive_ids":gold,"risk_ranked_picks":picks,"random_stratified_picks":random_picks,
             "risk_gold_positive_ids":risk_gold,"risk_recall":recall,"minimum_recall":.70,
             "required_hero_ids":FORCED,"prohibited_features":["age","birth_year","language","accent","asr_confidence","site","demographics"]}
