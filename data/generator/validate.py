"""Independent validation for the generated ConductAI data foundation."""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent; ROOT=HERE.parent; OUT=ROOT/"generated"; CORPUS=ROOT/"corpus"
sys.path.insert(0,str(HERE))
import capabilities, derived
from common import EVENTS, DOCUMENTS, SCHEMAS, STRUCTURED, parse_utc

errors=[]; checks=0
def ok(condition,msg):
    global checks; checks+=1
    if not condition: errors.append(msg)
def read_csv(name): return list(csv.DictReader((OUT/"structured"/f"{name}.csv").open()))
def read_jsonl(path): return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def corpus_checks():
    index=json.load((CORPUS/"index.json").open()); ok(len(index)==53,f"corpus expected 53 docs, got {len(index)}")
    required={"doc_id","version","title","family","effective_from","effective_to","status","supersedes","superseded_by","provenance","owner","path"}
    clauses=set()
    for d in index:
        ok(set(d)==required,f"bad corpus metadata {d.get('path')}"); p=CORPUS/d["path"]; ok(p.exists(),f"missing corpus file {p}")
        text=p.read_text(); ok(text.startswith("---\n"),f"front matter missing {p}")
        for c in re.findall(r"^#{2,3} §([^\s]+)",text,re.M): clauses.add(f'{d["doc_id"]}@{d["version"]} §{c}')
    ok(len(list((CORPUS/"skills").glob("*.md")))==11,"expected 11 skills")
    for gt in (OUT/"ground_truth"/"cases").glob("*.json"):
        for cite in json.load(gt.open()).get("must_cite",[]): ok(cite in clauses,f"missing cited clause {cite} ({gt.name})")


def schema_and_joins():
    tables={}
    for name in STRUCTURED:
        p=OUT/"structured"/f"{name}.csv"; ok(p.exists(),f"missing {p}");
        with p.open() as f: reader=csv.DictReader(f); ok(reader.fieldnames==[x for x in SCHEMAS[name] if x!="is_hero"],f"header drift {name}"); tables[name]=list(reader)
    for name in EVENTS:
        rows=read_jsonl(OUT/"events"/f"{name}.jsonl"); tables[name]=rows
        ok(all(set(r)==set(x for x in SCHEMAS[name] if x!="is_hero") for r in rows),f"schema drift {name}")
    for name,file in (("crm_notes","crm_notes"),("internal_comms","internal_comms"),("complaint_narratives","complaints")):
        rows=read_jsonl(OUT/"documents"/f"{file}.jsonl"); tables[name]=rows
        ok(all(set(r)==set(x for x in SCHEMAS[name] if x!="is_hero") for r in rows),f"schema drift {name}")
    ids={t:{r[SCHEMAS[t][0]] for r in rows} for t,rows in tables.items()}
    for a in tables["accounts"]: ok(a["customer_id"] in ids["customers"],f"orphan account {a['account_id']}")
    for i in tables["interactions"]:
        ok(i["customer_id"] in ids["customers"] and i["account_id"] in ids["accounts"] and i["colleague_id"] in ids["colleagues"],f"orphan interaction {i['interaction_id']}")
    joins={"offers":"interaction_id","enrollments":"source_interaction_id","product_changes":"source_interaction_id",
           "credit_line_requests":"interaction_id","installment_plans":"interaction_id","scanner_flags":"interaction_id","qa_reviews":"interaction_id"}
    for table,key in joins.items():
        for r in tables[table]: ok(r[key] in ids["interactions"],f"orphan {table} {r[SCHEMAS[table][0]]}")
    for b in tables["bureau_inquiries"]: ok(b["credit_request_id"] in ids["credit_line_requests"],f"orphan inquiry {b['inquiry_id']}")
    # All agent-visible records must have availability and no evaluator markers.
    for table,rows in tables.items():
        for r in rows:
            ok("is_hero" not in r,f"is_hero leaked into {table}")
            ok("ground_truth" not in json.dumps(r).lower() and "simulation" not in r,f"evaluator leakage in {table}")
    return tables


def transcript_checks(tables):
    interactions={x["interaction_id"]:x for x in tables["interactions"]}; files=list((OUT/"transcripts").glob("*.json")); ok(len(files)==len(interactions),"transcript count mismatch")
    for p in files:
        tr=json.load(p.open()); i=interactions[tr["interaction_id"]]; duration=(parse_utc(i["ended_at_utc"])-parse_utc(i["started_at_utc"])).total_seconds()
        last=-1
        for turn in tr["turns"]:
            ok(turn["start_s"]>=0 and turn["end_s"]<=duration+.01,f"turn outside interaction {p.stem}:{turn['turn_id']}")
            ok(turn["start_s"]>=last-.01,f"turn overlap/order {p.stem}:{turn['turn_id']}"); last=turn["end_s"]
            for w in turn["words"]: ok(turn["start_s"]<=w["start_s"]<=w["end_s"]<=turn["end_s"]+.01,f"word timing {p.stem}:{turn['turn_id']}")


def arithmetic_and_discovery(tables):
    planted=json.load((OUT/"ground_truth"/"planted_structures.json").open())
    p=planted["c04_stale_script"]; ok(p["affected"]==41 and len(p["affected_ids"])==41,"C04 affected count"); ok(len(p["correct_warning_ids"])==6,"C04 controls")
    # Reconstruct C04 from hard inquiries and transcript warning language.
    hard={b["credit_request_id"] for b in tables["bureau_inquiries"] if b["inquiry_type"]=="HARD"}; cr={r["credit_request_id"]:r for r in tables["credit_line_requests"]}
    affected=[]; controls=[]
    for qid in hard:
        if qid not in cr: continue
        iid=cr[qid]["interaction_id"]
        if not (iid=="INT-9000501" or iid.startswith("INT-004")): continue
        text=" ".join(t["text"] for t in json.load((OUT/"transcripts"/f"{iid}.json").open())["turns"]).lower()
        (controls if "hard inquiry" in text else affected).append(iid)
    ok(len(affected)==41 and len(controls)==6,f"C04 discoverability {len(affected)}/{len(controls)}")
    ok(planted["c10_asr_window"]["wrong_model_count"]==63 and len(planted["c10_asr_window"]["interaction_ids"])==63,"C10 ASR population")
    ok(planted["c12_shared_material"]["affected"]==15 and len(planted["c12_shared_material"]["semantic_hits"])==17 and len(planted["c12_shared_material"]["discarded"])==2,"C12 phrase population")
    ok(planted["c15_preference_sync"]["solicited"]==9 and len(planted["c15_preference_sync"]["solicited_ids"])==9,"C15 solicited count")
    ok(planted["c16_post_call"]["count"]==6 and len(planted["c16_post_call"]["lookback_ids"])==6,"C16 post-call count")
    ok(planted["c18_recorder"]["affected_calls"]==23 and len(planted["c18_recorder"]["affected_ids"])==23 and len(planted["c18_recorder"]["sales_ids"])==4,"C18 recorder population")
    enroll=defaultdict(lambda:[0,0])
    for r in tables["enrollments"]:
        enroll[r["source_colleague_id"]][0]+=1; enroll[r["source_colleague_id"]][1]+=bool(r["cancelled_at"])
    rates={c:k/n for c,(n,k) in enroll.items() if n>=10}; ok(max(rates,key=rates.get)=="COL-4421","C11 is not highest cancellation rate")
    vals=list(rates.values()); mean=sum(vals)/len(vals); sd=math.sqrt(sum((x-mean)**2 for x in vals)/len(vals)); ok(abs(rates["COL-4425"]-mean)<=sd,f"C11b outside 1 sd ({rates['COL-4425']}, {mean}, {sd})")
    c5=json.load((OUT/"ground_truth"/"cases"/"REV-2026-90006.json").open()); f=c5["key_facts"][0]; ok(str(derived.pct_fee(6200,5))==f["submitted_fee"] and str(derived.pct_fee(6200,3))==f["represented_fee"],"C05 fee arithmetic")
    c20=json.load((OUT/"ground_truth"/"cases"/"REV-2026-90023.json").open()); ok(abs(c20["key_facts"][0]["wpm"]-312.3)<.1,"C20 WPM")
    ok(derived.latest_safe_decision("2026-11-11","2026-11-11")=="2026-11-25","C18 SLA")


def labels_capabilities_fairness(tables):
    labs=read_jsonl(OUT/"ground_truth"/"background_labels.jsonl"); nonhero=[x for x in labs if x["source"]!="hero"]
    mis=[x for x in nonhero if x["gold_status"]=="misconduct"]
    rate=len(mis)/6500; ok(abs(rate-.036)<=.002,f"background misconduct prevalence {rate:.4f}")
    cov=json.load((OUT/"ground_truth"/"capability_coverage.json").open()); ok(set(cov)==set(capabilities.CAPABILITIES),"capability set drift")
    for cap,spec in cov.items(): ok(len(spec["primary"])>=3,f"{cap} has fewer than 3 primary cases")
    rb=json.load((OUT/"ground_truth"/"reviewer_baseline.json").open())
    targets={"R-A":(.79,.76),"R-B":(.74,.71),"R-C":(.75,.77)}
    for r,(p,rec) in targets.items():
        got=rb["reviewers"][r]; ok(abs(got["precision"]-p)<=.03 and abs(got["recall"]-rec)<=.03,f"reviewer {r} calibration")
    q=json.load((OUT/"ground_truth"/"Q01_sweep.json").open()); ok(len(q["risk_ranked_picks"])==36 and len(q["random_stratified_picks"])==4,"Q01 capacity"); ok(q["risk_recall"]>=q["minimum_recall"],f"Q01 recall {q['risk_recall']}"); ok(set(q["required_hero_ids"])<=set(q["risk_ranked_picks"]),"Q01 hero ranking")
    # Language and age-band rates must remain within broad sampling-noise bounds.
    customers={r["customer_id"]:r for r in tables["customers"]}; inter={r["interaction_id"]:r for r in tables["interactions"]}; positive={x["interaction_id"] for x in mis}
    groups=defaultdict(lambda:[0,0])
    for x in nonhero:
        c=customers[inter[x["interaction_id"]]["customer_id"]]; key=(c["language_preference"],int(c["birth_year"])//10)
        groups[key][0]+=1; groups[key][1]+=x["interaction_id"] in positive
    overall=rate
    for key,(n,k) in groups.items():
        if n>=100: ok(abs(k/n-overall)<.035,f"fairness imbalance {key}: {k/n:.3f}")


def main():
    ok((OUT/"manifest.json").exists(),"manifest missing"); corpus_checks(); tables=schema_and_joins(); transcript_checks(tables); arithmetic_and_discovery(tables); labels_capabilities_fairness(tables)
    if errors:
        print(f"FAILED: {len(errors)} of {checks} checks")
        for e in errors[:50]: print(f" - {e}")
        raise SystemExit(1)
    print(f"PASS: {checks} checks across corpus, schemas, joins, timing, arithmetic, discoverability, calibration, fairness, and leakage")


if __name__=="__main__": main()
