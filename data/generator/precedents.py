"""Forty deterministic precedent summaries, including required contrasts."""
from __future__ import annotations

from common import Ctx

SPECIAL={
 "PRE-0017":("Closing and general credit factors","no_error","The colleague said closing could affect utilization and length of history, without predicting a score."),
 "PRE-0022":("Correct three-percent balance transfer","no_error","Under CHC-BT v4, the colleague stated three percent on a genuine three-percent offer."),
 "PRE-0031":("Reservist referral omitted","no_error","The legacy reviewer assumed a reservist was ineligible before active duty. This conclusion conflicts with the current referral SOP."),
 "PRE-0044":("Cancellation not processed","substantiated","Two clear closure requests were not processed; MC-06 was substantiated."),
}


def build(ctx: Ctx):
    for n in range(1,41):
        pid=f"PRE-{n:04d}"; title,outcome,reason=SPECIAL.get(pid,(f"Conduct precedent {n}","substantiated" if n%4==0 else "no_error","Evidence was weighed against the policy effective on the interaction date."))
        ctx.precedents[pid]={"meta":{"precedent_id":pid,"review_id":f"HIST-{n:04d}","interaction_ids":[f"INT-H{n:04d}"],
            "decided_at":f"2026-{1+(n%8):02d}-{1+(n%27):02d}T18:00:00Z","glossary_version":"CLB-GLOSS@v6" if n<25 else "CLB-GLOSS@v7",
            "script_versions":[],"categories":[f"MC-{1+n%11:02d}"],"outcome":{"customer":outcome,"colleague":outcome,"control":"none"},
            "flawed":pid in ("PRE-0031","PRE-0037")},
            "body":f"# {title}\n\n## Facts\n\nSynthetic historical review.\n\n## Evidence\n\nTranscript and system-of-record data were compared.\n\n## Reasoning\n\n{reason}\n\n## Distinguishing facts\n\nApply only when dates, policy versions, and decisive evidence match."}
