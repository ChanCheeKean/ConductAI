"""Required architecture capabilities and the cases that need them (catalog §2).

Single source of truth for `required_capabilities` in each ground-truth file and for
ground_truth/capability_coverage.json. necessity: primary = the case cannot be solved correctly without it;
supporting = used in the expected solution but not decisive.
"""
from __future__ import annotations

ALL_CASES = ["C01", "C02", "C02b", "C03", "C04", "C05", "C06", "C07", "C07b", "C08", "C09", "C10", "C11", "C11b",
             "C12", "C13", "C14", "C15", "C16", "C17", "C18", "C19", "C20", "Q01"]

CAPABILITIES = {
    "agents": dict(
        label="Agents", signals=["plan_created", "plan_updated (agent-initiated)", "hypothesis_updated"],
        primary={"C06": "re-route a fee request into a product-change review from desktop evidence",
                 "C11": "turn one complaint into a colleague lookback when statistics suggest a pattern",
                 "C12": "chase a phrase from one chat to shared supervisor material",
                 "C14": "weigh behavioral vulnerability cues against explicit assent"},
        supporting=["C04", "C05", "C08", "C17"]),
    "router": dict(
        label="Router", signals=["route_decision {route_id, method, confidence, track, language, depth}"],
        primary={"C02": "outbound + sale must route to the callback-exception check, not straight to MC-07",
                 "C03": "a phrase hit on a true statement must take the L1 fast path",
                 "C10": "a Spanish call on the wrong ASR model must route to the Spanish review path",
                 "C13": "a servicing call with a complaint must take the servicing-conduct track",
                 "C15": "solicitation after opt-out must route to a preference-sync check",
                 "Q01": "portfolio selection is routing over a week of interactions"},
        supporting=["C02b", "C08", "C09"]),
    "loop_termination": dict(
        label="Loop engineering (real termination conditions)",
        signals=["termination {reason}", "wait_suspended {until, latest_safe_decision}", "wait_resumed",
                 "no_progress_detected"],
        primary={"C01": "suspend for the re-transcription and resume before the SLA",
                 "C03": "stop early once the inquiry record confirms the statement",
                 "C06": "wait for the colleague statement and the customer's reply",
                 "C17": "wait for the customer's confirmation inside the refund window",
                 "C18": "decide at the latest safe time after audio recovery fails"},
        supporting=["C10", "C13", "C15"]),
    "agent_graph": dict(
        label="Agent graph engineering", signals=["node_entered / node_exited", "edge_taken {from, to} incl. back-edges"],
        primary={"C04": "verify → re-plan back-edge when the script contradicts the policy",
                 "C06": "re-route edge plus the panel node",
                 "C11": "re-plan from a single interaction into a lookback",
                 "C12": "re-plan from individual conduct to systemic material",
                 "C14": "panel node ending in the conservative default"},
        supporting=["C05", "C08", "C18"]),
    "subagents": dict(
        label="Subagents", signals=["subagent_started {name, parent_span_id}", "subagent_finished", "panel_position / adjudication"],
        primary={"C06": "independent customer and colleague advocates plus adjudicator",
                 "C11": "one reviewer per enrollment interaction (22)",
                 "C12": "one verifier per phrase hit (17)",
                 "C14": "adversarial panel on a vulnerability judgment",
                 "Q01": "per-candidate scoring under a review budget"},
        supporting=["C04", "C08"]),
    "tool_calling": dict(
        label="Tool / function calling", signals=["tool_call {tool, args, rationale}", "tool_result {status, source_ids}"],
        primary={"C01": "request_retranscription is the only way to resolve the ASR conflict",
                 "C05": "the submitted offer is only visible through the order-system tools",
                 "C16": "the enrollment timestamp comes from the enrollment record tool",
                 "C20": "word timings come from get_transcript"},
        supporting=[c for c in ALL_CASES if c not in ("C01", "C05", "C16", "C20")]),
    "harness": dict(
        label="Harness", signals=["clock_advanced", "artifact_arrived {id}", "persona_reply", "colleague_statement_arrived"],
        primary={"C01": "the re-transcription is released 4 hours after the request",
                 "C06": "colleague statement and customer reply arrive on the virtual clock",
                 "C10": "the Spanish re-transcription arrives on the SLA day",
                 "C15": "the customer's choice arrives as a persona reply",
                 "C17": "the closure confirmation arrives as a persona reply",
                 "C18": "audio recovery result and customer reply arrive later",
                 "Q01": "a week of interactions as of Monday morning"},
        supporting=["C04"]),
    "skills": dict(
        label="Skills", signals=["skill_loaded {skill}"],
        primary={"C05": "balance-transfer disclosure playbook (fee % and $ under CHC-BT v5)",
                 "C08": "hardship-and-vulnerability playbook (no credit sales in HRP)",
                 "C09": "SCRA playbook (referral duty, 6% cap covers cards)",
                 "C13": "complaints playbook (definition independent of the word)",
                 "C17": "retention playbook (second request, no score predictions)"},
        supporting=["C06", "C10", "C11", "C14", "C19"]),
    "memory_persistent": dict(
        label="Memory — persistent (SQLite system of record)", signals=["sql_query / get_* with row IDs in tool_result"],
        primary={"C02": "callback request purpose, window and consent",
                 "C05": "offer submitted vs offer presented",
                 "C07b": "event timestamps and workstation clock offsets",
                 "C15": "preference set vs synced timestamps",
                 "C16": "local enrollment time and tz",
                 "Q01": "week population and permitted risk signals"},
        supporting=["C04", "C11", "C17"]),
    "memory_graph": dict(
        label="Memory — graph", signals=["graph_query {cypher, node_ids}", "graph_write {node|edge, status}"],
        primary={"C02": "outbound call → callback request → originating chat",
                 "C02b": "the same traversal must reveal a different purpose",
                 "C08": "call → customer → earlier hardship chat",
                 "C11": "colleague → enrollments → cancellations → complaints; pattern write",
                 "C11b": "scope boundary: no traversal from a teammate's pattern",
                 "C12": "colleagues → team → supervisor → internal message"},
        supporting=["C15", "C16"]),
    "memory_semantic": dict(
        label="Memory — semantic / vector",
        signals=["retrieval {query, filters: as_of/status/validity/speaker, doc_ids, used/discarded}"],
        primary={"C04": "script sentence and paraphrases across the population; policy and script as of date",
                 "C09": "SCRA text and SOP retrieval",
                 "C12": "paraphrase search over colleague transcript segments",
                 "C17": "look-alike precedents to distinguish",
                 "C19": "glossary condition as of the interaction date"},
        supporting=["C05", "C10", "C13", "C14"]),
    "sandbox": dict(
        label="Sandbox / REPL", signals=["computation {code, inputs, output}"],
        primary={"C04": "population count with exclusions", "C05": "BT fee arithmetic",
                 "C07b": "clock-offset and time-zone alignment", "C10": "Flex fee check",
                 "C11": "cancellation rate vs program (binomial)", "C16": "Phoenix local time to UTC vs call end",
                 "C18": "latest safe decision with holidays", "C20": "words per minute from word timings",
                 "Q01": "risk scores and seeded random slice"},
        supporting=["C06", "C12", "C17"]),
    "read_paths": dict(
        label="Agent read paths (selective read)", signals=["memory_read {filters}", "memory_verified / memory_rejected {note_id, reason}"],
        primary={"C04": "reject MEM-0310 as stale under CLI v6", "C10": "do not read language as risk",
                 "C11b": "reject a teammate-scoped pattern note", "C14": "reject the prohibited age note",
                 "C19": "reject the over-generalized consolidated note"},
        supporting=["C07", "C12", "C18"]),
    "write_paths": dict(
        label="Agent write paths (selective write, consolidation, forgetting)",
        signals=["memory_write / supersede / retract / consolidate / purge", "memory_write_skipped", "write_rejected",
                 "graph_write", "automated_action"],
        primary={"C03": "skip: a true statement is not new knowledge", "C04": "supersede MEM-0310",
                 "C11": "consolidate raw notes + pattern graph write", "C11b": "log the decision not to write",
                 "C12": "consolidate observations + material graph write", "C14": "purge MEM-0396",
                 "C19": "supersede MEM-0350 and re-consolidate"},
        supporting=["C01", "C06", "C07", "C10"]),
}
MIN_PRIMARY = 3


def required_capabilities(case: str) -> list:
    out = []
    for cap, spec in CAPABILITIES.items():
        if case in spec["primary"]:
            out.append(dict(capability=cap, necessity="primary", why=spec["primary"][case],
                            trajectory_signals=spec["signals"]))
        elif case in spec["supporting"]:
            out.append(dict(capability=cap, necessity="supporting", why=f"used in the expected {case} path",
                            trajectory_signals=spec["signals"]))
    return out


def coverage() -> dict:
    return {cap: dict(label=s["label"], primary=sorted(s["primary"]), supporting=sorted(s["supporting"]),
                      trajectory_signals=s["signals"]) for cap, s in CAPABILITIES.items()}
