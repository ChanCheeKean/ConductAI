"""Generate the ConductAI synthetic conduct-review dataset.

Usage:  python3 data/generator/gen.py                    (writes data/generated/)
        CONDUCT_OUT=/tmp/x python3 data/generator/gen.py --only heroes.cases_a   (development: world + people + listed modules)
Deterministic: same SEED -> byte-identical output. No network, no wall-clock reads.
"""
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import capabilities  # noqa: E402
import people  # noqa: E402
import world  # noqa: E402
from common import (AS_OF_ISO, DOCUMENTS, EVENTS, OUT_DIR, SCHEMAS, SEED, STRUCTURED, Ctx, sorted_rows,  # noqa: E402
                    visible, write_csv, write_json, write_jsonl, write_text)

HERO_MODULES = ["heroes.cases_a", "heroes.cases_b", "heroes.cases_c", "heroes.cases_d", "heroes.cases_e"]
# Pipeline order. Each module exposes build(ctx); hero modules may also expose finalize(ctx), run after the
# background so population-dependent ground truth is computed over the final records.
PIPELINE = HERO_MODULES + ["background", "oversight", "precedents", "memory_seed", "sweep", "graph"]
DOCUMENT_FILES = {"crm_notes": "crm_notes", "internal_comms": "internal_comms", "complaint_narratives": "complaints"}


def _module_exists(name: str) -> bool:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.exists(os.path.join(here, *name.split(".")) + ".py")


def build(only=None) -> tuple:
    ctx = Ctx(SEED)
    world.build(ctx)
    people.build(ctx)
    wanted = [m for m in PIPELINE if only is None or m in only]
    missing = [m for m in wanted if not _module_exists(m)]
    mods = [importlib.import_module(m) for m in wanted if m not in missing]
    for mod in mods:
        mod.build(ctx)
    for mod in mods:
        if hasattr(mod, "finalize"):
            mod.finalize(ctx)
    for gt in ctx.ground_truth.values():
        gt["required_capabilities"] = capabilities.required_capabilities(gt["code"])
    if ctx.q01:
        ctx.q01["required_capabilities"] = capabilities.required_capabilities("Q01")
    return ctx, missing


def _front_matter(meta: dict) -> str:
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {v}" if isinstance(v, (int, float)) and not isinstance(v, bool) else
                     f"{k}: {__import__('json').dumps(v, ensure_ascii=False)}")
    return "\n".join(lines + ["---", ""])


def write(ctx: Ctx, missing: list) -> dict:
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    S = lambda *p: os.path.join(OUT_DIR, *p)  # noqa: E731
    for table in STRUCTURED:
        cols = [c for c in SCHEMAS[table] if c != "is_hero"]
        write_csv(S("structured", f"{table}.csv"), cols, sorted_rows(table, ctx.t[table]))
    for table in EVENTS:
        write_jsonl(S("events", f"{table}.jsonl"), [visible(r) for r in sorted_rows(table, ctx.t[table])])
    for table, fname in DOCUMENT_FILES.items():
        write_jsonl(S("documents", f"{fname}.jsonl"), [visible(r) for r in sorted_rows(table, ctx.t[table])])
    for iid, tr in sorted(ctx.transcripts.items()):
        write_json(S("transcripts", f"{iid}.json"), tr)
    for kind, items in sorted(ctx.on_request.items()):
        for aid, art in sorted(items.items()):
            write_json(S("on_request", kind, f"{aid}.json"), art)
    write_json(S("simulation", "customer_personas.json"), [ctx.personas[k] for k in sorted(ctx.personas)])
    for pid, p in sorted(ctx.precedents.items()):
        meta = {k: v for k, v in p["meta"].items() if k != "flawed"}
        write_text(S("precedents", f"{pid}.md"), _front_matter(meta) + p["body"].strip() + "\n")
    write_jsonl(S("memory_seed", "agent_memory_notes.jsonl"), sorted(ctx.memory_notes, key=lambda n: n["note_id"]))
    for tid, steps in sorted(ctx.run_traces.items()):
        write_jsonl(S("memory_seed", "run_traces", f"{tid}.jsonl"), steps)
    for name, (header, rows) in world.reference_tables().items():
        write_csv(S("reference", f"{name}.csv"), header, [dict(zip(header, r)) for r in rows])
    nodes, edges = getattr(ctx, "graph", ([], []))
    write_jsonl(S("graph", "nodes.jsonl"), nodes)
    write_jsonl(S("graph", "edges.jsonl"), edges)
    # evaluator-only
    for rid, gt in sorted(ctx.ground_truth.items()):
        write_json(S("ground_truth", "cases", f"{rid}.json"), gt)
    write_jsonl(S("ground_truth", "background_labels.jsonl"), [ctx.bg_labels[k] for k in sorted(ctx.bg_labels)])
    write_json(S("ground_truth", "capability_coverage.json"), capabilities.coverage())
    write_json(S("ground_truth", "planted_structures.json"), ctx.planted)
    write_json(S("ground_truth", "precedent_flags.json"),
               {pid: bool(p["meta"].get("flawed")) for pid, p in sorted(ctx.precedents.items())})
    if ctx.q01:
        write_json(S("ground_truth", "Q01_sweep.json"), ctx.q01)
    if getattr(ctx, "reviewer_baseline", None):
        write_json(S("ground_truth", "reviewer_baseline.json"), ctx.reviewer_baseline)
    hero_index = {t: sorted(r[SCHEMAS[t][0]] for r in ctx.t[t] if r["is_hero"]) for t in SCHEMAS if ctx.t[t]}
    write_json(S("ground_truth", "hero_index.json"), {k: v for k, v in hero_index.items() if v})
    counts = {t: len(ctx.t[t]) for t in SCHEMAS}
    counts.update(transcripts=len(ctx.transcripts), precedents=len(ctx.precedents), memory_notes=len(ctx.memory_notes),
                  run_traces=len(ctx.run_traces), personas=len(ctx.personas), graph_nodes=len(nodes),
                  graph_edges=len(edges), hero_cases=len(ctx.ground_truth), background_labels=len(ctx.bg_labels),
                  **{f"on_request_{k}": len(v) for k, v in sorted(ctx.on_request.items())})
    manifest = dict(
        dataset="ConductAI synthetic conduct-review ecosystem (Copperlake Bank, N.A.)", seed=SEED, as_of=AS_OF_ISO,
        missing_modules=missing, counts=counts,
        on_request=sorted(ctx.on_request_log, key=lambda e: e["artifact_id"]),
        hero_cases={rid: dict(code=g["code"], title=g["title"], depth=g["depth"])
                    for rid, g in sorted(ctx.ground_truth.items())},
        paths=dict(structured="structured/*.csv", events="events/*.jsonl", transcripts="transcripts/<interaction_id>.json",
                   documents="documents/*.jsonl", on_request="on_request/<kind>/<id>.json",
                   simulation="simulation/customer_personas.json", precedents="precedents/*.md",
                   memory_seed="memory_seed/", reference="reference/*.csv", graph="graph/{nodes,edges}.jsonl",
                   ground_truth="ground_truth/ (evaluator only)"))
    write_json(S("manifest.json"), manifest)
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="pipeline modules to run (world and people always run)")
    args = ap.parse_args()
    c, miss = build(set(args.only) if args.only is not None else None)
    man = write(c, miss)
    if miss:
        print(f"WARNING: modules not present yet: {', '.join(miss)}")
    for k, v in man["counts"].items():
        if v:
            print(f"{k:32s} {v}")
