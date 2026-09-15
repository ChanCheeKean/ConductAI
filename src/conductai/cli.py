"""Local run and trajectory replay CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from conductai.app import build_runtime
from conductai.observability.replay import read_events, replay_assessment
from conductai.observability.schema import export_schemas
from conductai.runtime.contracts import RunRequest


def main() -> None:
    parser = argparse.ArgumentParser(prog="conductai")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("scenario")
    run_parser.add_argument("--ledger", type=Path, default=Path("data/generated/runs.sqlite"))
    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("run_id")
    replay_parser.add_argument("--ledger", type=Path, default=Path("data/generated/runs.sqlite"))
    replay_parser.add_argument("--type")
    replay_parser.add_argument("--actor")
    replay_parser.add_argument("--through-seq", type=int)
    replay_parser.add_argument("--assessment", action="store_true")
    schema_parser = subparsers.add_parser("export-schema")
    schema_parser.add_argument("--output", type=Path, default=Path("docs/schemas"))
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "export-schema":
        output = args.output if args.output.is_absolute() else root / args.output
        export_schemas(output)
        print(output)
        return
    ledger_path = args.ledger if args.ledger.is_absolute() else root / args.ledger
    if args.command == "run":
        raw = yaml.safe_load((root / "config" / "scenarios" / f"{args.scenario.lower()}.yaml").read_text())
        request = RunRequest(**{key: raw[key] for key in RunRequest.model_fields})
        runtime, _ = build_runtime(root, ledger_path)
        handle = runtime.start(request)
        list(runtime.run_or_stream(handle))
        print(runtime.result(handle.run_id).model_dump_json(indent=2))
        return
    if args.assessment:
        print(json.dumps(replay_assessment(ledger_path, args.run_id, args.through_seq), indent=2))
        return
    for event in read_events(ledger_path, args.run_id, event_type=args.type,
                             actor=args.actor, through_seq=args.through_seq):
        print(f"{event.seq:04d} {event.type.value:28} {event.actor.name:28} {event.summary}")


if __name__ == "__main__":
    main()
