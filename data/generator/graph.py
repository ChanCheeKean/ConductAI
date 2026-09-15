"""Deterministic graph projection of agent-visible entities and explicit joins."""
from __future__ import annotations

import json
from collections import defaultdict
from common import Ctx, parse_utc


def build(ctx: Ctx): pass


def finalize(ctx: Ctx):
    nodes=[]; edges=[]; seen=set()
    def node(label,key,props=None):
        nid=f"{label}:{key}"
        if nid not in seen: nodes.append({"node_id":nid,"label":label,"key":key,"props":props or {}}); seen.add(nid)
        return nid
    def edge(src,rel,dst,props=None): edges.append({"src":src,"rel":rel,"dst":dst,"props":props or {}})
    for c in ctx.t["customers"]: node("Customer",c["customer_id"])
    for a in ctx.t["accounts"]: node("Account",a["account_id"]); edge(node("Customer",a["customer_id"]),"HOLDS",node("Account",a["account_id"]))
    for t in ctx.t["teams"]: node("Team",t["team_id"]); node("Site",t["site"]); edge(node("Team",t["team_id"]),"LOCATED_AT",node("Site",t["site"]))
    for c in ctx.t["colleagues"]:
        node("Colleague",c["colleague_id"]); edge(node("Colleague",c["colleague_id"]),"SUPERVISES" if c["role"]=="supervisor" else "MEMBER_OF",node("Team",c["team_id"]))
    by_customer=defaultdict(list)
    for i in ctx.t["interactions"]:
        x=node("Interaction",i["interaction_id"],{"channel":i["channel"],"started_at_utc":i["started_at_utc"]}); by_customer[i["customer_id"]].append(i)
        edge(node("Customer",i["customer_id"]),"PARTICIPATED",x,{"role":"customer"}); edge(node("Colleague",i["colleague_id"]),"PARTICIPATED",x,{"role":"colleague"}); edge(x,"ABOUT",node("Account",i["account_id"]))
    for rows in by_customer.values():
        rows.sort(key=lambda x:x["started_at_utc"])
        for a,b in zip(rows,rows[1:]): edge(node("Interaction",a["interaction_id"]),"NEXT_CONTACT",node("Interaction",b["interaction_id"]),{"gap_hours":round((parse_utc(b["started_at_utc"])-parse_utc(a["ended_at_utc"])).total_seconds()/3600,2)})
    for c in ctx.t["callback_requests"]:
        x=node("CallbackRequest",c["callback_request_id"]); edge(x,"CREATED_IN",node("Interaction",c["created_in_interaction_id"]));
        if c["fulfilled_by_interaction_id"]: edge(x,"FULFILLED_BY",node("Interaction",c["fulfilled_by_interaction_id"]))
    maps=[("offers","Offer","offer_instance_id","interaction_id","PRESENTED_IN"),("enrollments","Enrollment","enrollment_id","source_interaction_id","ENROLLED_IN"),("product_changes","ProductChange","product_change_id","source_interaction_id","CHANGED_IN"),("installment_plans","InstallmentPlan","plan_id","interaction_id","PLAN_CREATED_IN")]
    for table,label,key,ik,rel in maps:
        for r in ctx.t[table]: edge(node(label,r[key]),rel,node("Interaction",r[ik]))
    for c in ctx.t["complaints"]:
        x=node("Complaint",c["complaint_id"])
        for iid in c["related_interaction_ids"]: edge(x,"COMPLAINS_ABOUT",node("Interaction",iid))
    for m in ctx.t["internal_comms"]: edge(node("Colleague",m["author_id"]),"AUTHORED",node("InternalMessage",m["message_id"])); edge(node("InternalMessage",m["message_id"]),"SENT_TO",node("Team",m["team_id"]))
    ctx.graph=(sorted(nodes,key=lambda x:x["node_id"]),sorted(edges,key=lambda x:(x["src"],x["rel"],x["dst"])))
