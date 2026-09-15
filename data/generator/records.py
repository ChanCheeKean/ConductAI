"""Record constructors shared by hero builders, planted structures and the background generator.

Each helper adds one row (or one artifact) to the Ctx with consistent IDs, clocks and `available_at`.
Time conventions:
  * interactions are placed by local wall time in a stated tz and stored in UTC;
  * desktop events are stored as the colleague workstation's local reading (site tz + workstation offset);
  * enrollments are stored as local site time + tz (deliberately not UTC);
  * everything else is UTC ISO (`...Z`) or an ISO date.
"""
from __future__ import annotations

from typing import Optional

import derived
import world
from common import (Ctx, add_seconds, local_to_utc, m, stable_hex, utc_to_local)
from transcripts import Transcript

CITY = {c[0]: c for c in world.CITIES}


def num(entity_id: str) -> str:
    """'INT-9000101' -> '9000101'."""
    return entity_id.split("-", 1)[1]


def _seq(ctx: Ctx, kind: str, inter: dict) -> int:
    key = f"{kind}:{inter['interaction_id']}"
    ctx.counters[key] += 1
    return ctx.counters[key]


def opaque_id(ctx: Ctx, prefix: str, table: str, *key, width: int = 7) -> str:
    """Deterministic non-sequential background-range ID ('INT-0xxxxxx'); collisions bump upward."""
    n = int(stable_hex(prefix, *key, n=12), 16) % (10 ** (width - 1))
    while True:
        cand = f"{prefix}-0{n:0{width - 1}d}"
        if not ctx.has(table, cand):
            return cand
        n = (n + 1) % (10 ** (width - 1))


# ---------------------------------------------------------------- people and accounts
def customer(ctx: Ctx, customer_id: str, first: str, last: str, city: str, *, birth_year: int, since: str,
             language: str = "en", trusted_contact: bool = False, military: str = "none", is_hero: bool = False) -> dict:
    c = CITY[city]
    tail = int(num(customer_id)) % 100
    return ctx.add("customers", dict(
        customer_id=customer_id, first_name=first, last_name=last, birth_year=birth_year, city=city, state=c[1],
        zip=f"{c[2]}{tail:02d}", email=f"{first.lower()}.{last.lower()}{tail:02d}@example.com".replace(" ", ""),
        phone=f"({c[4]}) 555-01{tail:02d}", language_preference=language, customer_since=since,
        trusted_contact_on_file=trusted_contact, military_status_on_file=military,
        available_at=local_to_utc(since, "09:00:00", c[3]), is_hero=is_hero))


def customer_tz(cust: dict) -> str:
    return CITY[cust["city"]][3]


def account(ctx: Ctx, account_id: str, cust: dict, product: str, *, opened: str, credit_limit: int,
            rewards_balance: int = 0, statement_closing_day: int = 20, status: str = "open",
            annual_fee_posting_month: Optional[int] = None, is_hero: bool = False) -> dict:
    p = world.PRODUCTS[product]
    af_month = annual_fee_posting_month if annual_fee_posting_month is not None else (
        int(opened[5:7]) if p["annual_fee"] != "0.00" else "")
    return ctx.add("accounts", dict(
        account_id=account_id, customer_id=cust["customer_id"], product_code=product, opened_at=opened,
        credit_limit=credit_limit, annual_fee=p["annual_fee"], annual_fee_posting_month=af_month,
        statement_closing_day=statement_closing_day, status=status, purchase_apr=p["purchase_apr"],
        rewards_balance=rewards_balance, rewards_unit=p["rewards_unit"],
        available_at=local_to_utc(opened, "09:00:00", "America/Chicago"), is_hero=is_hero))


def flag(ctx: Ctx, flag_id: str, acct: dict, flag_name: str, set_at: str, *, cleared_at: str = "",
         set_by_interaction_id: str = "", source_system: str = "crm", is_hero: bool = False) -> dict:
    return ctx.add("account_flags", dict(flag_id=flag_id, account_id=acct["account_id"], flag=flag_name, set_at=set_at,
                                         cleared_at=cleared_at, set_by_interaction_id=set_by_interaction_id,
                                         source_system=source_system, available_at=set_at, is_hero=is_hero))


def preference(ctx: Ctx, pref_id: str, cust: dict, pref: str, value: str, set_at: str, *, set_by_interaction_id: str = "",
               sync_status: str = "synced", synced_to_desktop_at: Optional[str] = None, is_hero: bool = False) -> dict:
    synced = add_seconds(set_at, 90) if synced_to_desktop_at is None else synced_to_desktop_at
    return ctx.add("preferences", dict(pref_id=pref_id, customer_id=cust["customer_id"], preference=pref, value=value,
                                       set_at=set_at, set_by_interaction_id=set_by_interaction_id,
                                       sync_status=sync_status, synced_to_desktop_at=synced, available_at=set_at,
                                       is_hero=is_hero))


# ---------------------------------------------------------------- interactions
def interaction(ctx: Ctx, interaction_id: str, *, cust: dict, acct: dict, colleague_id: str, channel: str,
                start_local: str, tz: str, transcript: Transcript, disposition: str, duration_s: Optional[float] = None,
                direction: str = "inbound", outbound_reason: str = "none", callback_request_id: str = "",
                queue: str = "general", ivr_intent: str = "", recording_status: Optional[str] = None,
                recording_gaps: Optional[list] = None, detected_language: Optional[str] = None,
                is_hero: bool = False) -> dict:
    """start_local: 'YYYY-MM-DDTHH:MM:SS' in tz. Duration defaults to the transcript end + 4 s (phone) or + 60 s."""
    date_s, time_s = start_local.split("T")
    started = local_to_utc(date_s, time_s, tz)
    tail = 4.0 if channel == "phone" else 60.0
    dur = duration_s if duration_s is not None else transcript.end_s + tail
    ended = add_seconds(started, dur)
    phone = channel == "phone"
    ctx.transcripts[interaction_id] = transcript.data()
    return ctx.add("interactions", dict(
        interaction_id=interaction_id, channel=channel, direction=direction, outbound_reason=outbound_reason,
        callback_request_id=callback_request_id, customer_id=cust["customer_id"], account_id=acct["account_id"],
        colleague_id=colleague_id, queue=queue, ivr_intent=ivr_intent if phone else "", started_at_utc=started,
        ended_at_utc=ended, recording_status=(recording_status or "complete") if phone else "",
        recording_gaps=(recording_gaps or []) if phone else [], asr_model=transcript.asr_model,
        asr_mean_confidence=transcript.mean_conf() if phone else "",
        detected_language=detected_language or transcript.language, disposition_code=disposition,
        workstation_id=world.workstation(colleague_id)[0], available_at=ended, is_hero=is_hero))


def call_utc(inter: dict, offset_s: float) -> str:
    return derived.call_offset_to_utc(inter["started_at_utc"], offset_s)


def desktop(ctx: Ctx, inter: dict, offset_s: float, event_type: str, payload: Optional[dict] = None, *,
            seq: Optional[int] = None) -> dict:
    """Desktop event at a true call offset; stored as the workstation's (possibly skewed) local reading."""
    col = inter["colleague_id"]
    ws, ws_offset = world.workstation(col)
    tz = world.site_tz(col)
    true_utc = call_utc(inter, offset_s)
    n = seq if seq is not None else _seq(ctx, "DEV", inter)
    return ctx.add("desktop_events", dict(
        event_id=f"DEV-{num(inter['interaction_id'])}-{n:02d}", interaction_id=inter["interaction_id"],
        colleague_id=col, workstation_id=ws, ts_local=derived.desktop_reading(true_utc, tz, ws_offset), tz=tz,
        type=event_type, payload=payload or {}, available_at=add_seconds(true_utc, 60), is_hero=inter["is_hero"]))


def ievent(ctx: Ctx, inter: dict, event_type: str, offset_s: float, end_offset_s: Optional[float] = None,
           detail: Optional[dict] = None) -> dict:
    n = _seq(ctx, "IEV", inter)
    return ctx.add("interaction_events", dict(
        event_id=f"IEV-{num(inter['interaction_id'])}-{n:02d}", interaction_id=inter["interaction_id"], type=event_type,
        offset_s=offset_s, end_offset_s="" if end_offset_s is None else end_offset_s, detail=detail or {},
        available_at=inter["ended_at_utc"], is_hero=inter["is_hero"]))


def account_event(ctx: Ctx, event_id: str, acct: dict, event_type: str, ts_utc: str, detail: Optional[dict] = None,
                  is_hero: bool = False) -> dict:
    return ctx.add("account_events", dict(event_id=event_id, account_id=acct["account_id"], type=event_type,
                                          ts_utc=ts_utc, detail=detail or {}, available_at=ts_utc, is_hero=is_hero))


def callback(ctx: Ctx, callback_request_id: str, cust: dict, created_in: dict, *, created_by: str, purpose: str,
             window_start_local: str, window_end_local: str, tz: str, consent: bool, fulfilled_by: str = "") -> dict:
    return ctx.add("callback_requests", dict(
        callback_request_id=callback_request_id, customer_id=cust["customer_id"],
        created_in_interaction_id=created_in["interaction_id"], created_by=created_by, purpose=purpose,
        requested_window_start=window_start_local, requested_window_end=window_end_local, requested_tz=tz,
        consent_to_call=consent, phone=cust["phone"], fulfilled_by_interaction_id=fulfilled_by,
        available_at=created_in["ended_at_utc"], is_hero=created_in["is_hero"]))


# ---------------------------------------------------------------- sales and servicing records
def offer(ctx: Ctx, offer_instance_id: str, inter: dict, acct: dict, offer_code: str, offer_type: str, *,
          presented_offset: float, accepted: bool, submitted_offset: Optional[float] = None, amount="",
          fee_rate="", fee_amount="", promo_apr="", promo_months="", eligibility_result: str = "ELIGIBLE",
          firm_offer_valid_through: str = "", displayed_offset: Optional[float] = None) -> dict:
    submitted = call_utc(inter, submitted_offset) if submitted_offset is not None else ""
    return ctx.add("offers", dict(
        offer_instance_id=offer_instance_id, interaction_id=inter["interaction_id"], account_id=acct["account_id"],
        offer_code=offer_code, offer_type=offer_type, presented_at_utc=call_utc(inter, presented_offset),
        eligibility_result=eligibility_result, accepted=accepted, submitted_at_utc=submitted,
        amount=m(amount) if amount != "" else "", fee_rate=fee_rate, fee_amount=m(fee_amount) if fee_amount != "" else "",
        promo_apr=promo_apr, promo_months=promo_months, firm_offer_valid_through=firm_offer_valid_through,
        displayed_on_desktop_at_utc=call_utc(inter, displayed_offset) if displayed_offset is not None else "",
        available_at=submitted or inter["ended_at_utc"], is_hero=inter["is_hero"]))


def enrollment(ctx: Ctx, enrollment_id: str, acct: dict, product: str, inter: dict, offset_s: float, *,
               status: str = "active", cancelled_at: str = "", cancel_reason: str = "", cancel_channel: str = "") -> dict:
    """offset_s is from call start and may exceed the call duration (post-call enrollment)."""
    tz = world.site_tz(inter["colleague_id"])
    at_utc = call_utc(inter, offset_s)
    return ctx.add("enrollments", dict(
        enrollment_id=enrollment_id, account_id=acct["account_id"], product=product,
        source_interaction_id=inter["interaction_id"], source_colleague_id=inter["colleague_id"],
        enrolled_at_local=utc_to_local(at_utc, tz), enrolled_tz=tz, status=status, cancelled_at=cancelled_at,
        cancel_reason=cancel_reason, cancel_channel=cancel_channel, available_at=add_seconds(at_utc, 120),
        is_hero=inter["is_hero"]))


def product_change(ctx: Ctx, product_change_id: str, acct: dict, inter: dict, offset_s: float, *, to_product: str,
                   rewards_before: int, rewards_after: str, conversion_value, benefits_removed: list,
                   annual_fee_effect: str) -> dict:
    at = call_utc(inter, offset_s)
    return ctx.add("product_changes", dict(
        product_change_id=product_change_id, account_id=acct["account_id"], from_product=acct["product_code"],
        to_product=to_product, submitted_at_utc=at, source_interaction_id=inter["interaction_id"],
        rewards_before=rewards_before, rewards_after=rewards_after, rewards_conversion_value=m(conversion_value),
        benefits_removed=benefits_removed, annual_fee_effect=annual_fee_effect, available_at=add_seconds(at, 120),
        is_hero=inter["is_hero"]))


def credit_request(ctx: Ctx, credit_request_id: str, acct: dict, inter: dict, offset_s: float, *, increase: int,
                   tenure_months: int, decision: str = "approved", income_verified: bool = True,
                   obligations_checked: bool = True) -> dict:
    at = call_utc(inter, offset_s)
    version = derived.cli_policy_version(at)
    return ctx.add("credit_line_requests", dict(
        credit_request_id=credit_request_id, account_id=acct["account_id"], interaction_id=inter["interaction_id"],
        requested_at_utc=at, requested_increase=increase, tenure_months_at_request=tenure_months,
        policy_version_applied=f"CLB-POL-CLI@{version}", decision=decision,
        new_limit=int(acct["credit_limit"]) + increase if decision == "approved" else acct["credit_limit"],
        income_verified=income_verified, obligations_checked=obligations_checked, available_at=add_seconds(at, 60),
        is_hero=inter["is_hero"]))


def bureau_inquiry(ctx: Ctx, inquiry_id: str, creq: dict, inquiry_type: str, *, bureau: str = "Equifax",
                   lag_days: int = 2) -> dict:
    pulled = add_seconds(creq["requested_at_utc"], 45)
    return ctx.add("bureau_inquiries", dict(
        inquiry_id=inquiry_id, credit_request_id=creq["credit_request_id"], account_id=creq["account_id"],
        inquiry_type=inquiry_type, bureau=bureau, pulled_at_utc=pulled,
        available_at=add_seconds(pulled, lag_days * 86400), is_hero=creq["is_hero"]))


def installment_plan(ctx: Ctx, plan_id: str, acct: dict, inter: dict, *, principal, months: int, rate_pct: str,
                     first_fee_date: str, status: str = "active") -> dict:
    return ctx.add("installment_plans", dict(
        plan_id=plan_id, account_id=acct["account_id"], interaction_id=inter["interaction_id"], principal=m(principal),
        months=months, monthly_fee_rate=rate_pct, monthly_fee_amount=m(derived.pct_fee(principal, rate_pct)),
        first_fee_date=first_fee_date, status=status, available_at=inter["ended_at_utc"], is_hero=inter["is_hero"]))


def fee(ctx: Ctx, ledger_id: str, acct: dict, posted_date: str, fee_type: str, amount, *, related_id: str = "",
        reason_code: str = "", source_interaction_id: str = "", is_hero: bool = False) -> dict:
    return ctx.add("fee_ledger", dict(
        ledger_id=ledger_id, account_id=acct["account_id"], posted_date=posted_date, type=fee_type, amount=m(amount),
        related_id=related_id, reason_code=reason_code, source_interaction_id=source_interaction_id,
        available_at=local_to_utc(posted_date, "06:00:00", "America/Chicago"), is_hero=is_hero))


def reward(ctx: Ctx, rewards_txn_id: str, acct: dict, posted_date: str, txn_type: str, amount, unit: str, *,
           related_id: str = "", is_hero: bool = False) -> dict:
    return ctx.add("rewards_ledger", dict(
        rewards_txn_id=rewards_txn_id, account_id=acct["account_id"], posted_date=posted_date, type=txn_type,
        amount=amount, unit=unit, related_id=related_id,
        available_at=local_to_utc(posted_date, "06:00:00", "America/Chicago"), is_hero=is_hero))


def statement(ctx: Ctx, statement_id: str, acct: dict, period_start: str, period_end: str, ending_balance, *,
              is_hero: bool = False) -> dict:
    sent = local_to_utc(period_end, "23:00:00", "America/Chicago")
    return ctx.add("statements", dict(statement_id=statement_id, account_id=acct["account_id"], period_start=period_start,
                                      period_end=period_end, ending_balance=m(ending_balance), transmitted_at=sent,
                                      available_at=sent, is_hero=is_hero))


def payment(ctx: Ctx, payment_id: str, acct: dict, amount, initiated_at: str, *, status: str = "posted",
            return_code: str = "", is_hero: bool = False) -> dict:
    return ctx.add("payments", dict(payment_id=payment_id, account_id=acct["account_id"], amount=m(amount),
                                    initiated_at=initiated_at, status=status, return_code=return_code,
                                    available_at=initiated_at, is_hero=is_hero))


# ---------------------------------------------------------------- documents
def complaint(ctx: Ctx, complaint_id: str, cust: dict, received_at: str, channel: str, *, logged_by: str,
              related_interaction_ids: list, category: str, text: str, status: str = "open",
              available_at: Optional[str] = None, is_hero: bool = False) -> dict:
    avail = available_at or received_at
    ctx.add("complaint_narratives", dict(complaint_id=complaint_id, received_at=received_at, channel=channel, text=text,
                                         available_at=avail, is_hero=is_hero))
    return ctx.add("complaints", dict(
        complaint_id=complaint_id, customer_id=cust["customer_id"], received_at=received_at, channel=channel,
        logged_by=logged_by, related_interaction_ids=related_interaction_ids, category=category, status=status,
        available_at=avail, is_hero=is_hero))


def crm_note(ctx: Ctx, inter: dict, text: str, *, delay_s: float = 45, note_id: Optional[str] = None) -> dict:
    at = add_seconds(inter["ended_at_utc"], delay_s)
    return ctx.add("crm_notes", dict(note_id=note_id or f"NOTE-{num(inter['interaction_id'])}",
                                     interaction_id=inter["interaction_id"], colleague_id=inter["colleague_id"],
                                     created_at_utc=at, text=text, available_at=at, is_hero=inter["is_hero"]))


def internal_message(ctx: Ctx, message_id: str, author_id: str, sent_at_utc: str, text: str, *,
                     channel: str = "team_chat", attachments: Optional[list] = None, is_hero: bool = False) -> dict:
    return ctx.add("internal_comms", dict(message_id=message_id, channel=channel, author_id=author_id,
                                          team_id=world.team_of(author_id), sent_at_utc=sent_at_utc, text=text,
                                          attachments=attachments or [], available_at=sent_at_utc, is_hero=is_hero))


def scanner_flag(ctx: Ctx, inter: dict, rule_id: str, flagged_at: str, *, matched_text: str = "",
                 matched_turn_id: str = "") -> dict:
    n = _seq(ctx, "SFL", inter)
    return ctx.add("scanner_flags", dict(flag_id=f"SFL-{num(inter['interaction_id'])}-{n:02d}",
                                         interaction_id=inter["interaction_id"], rule_id=rule_id, flagged_at=flagged_at,
                                         matched_text=matched_text, matched_turn_id=matched_turn_id,
                                         available_at=flagged_at, is_hero=inter["is_hero"]))


def incident(ctx: Ctx, incident_id: str, system: str, started: str, ended: str, description: str, affected_count: int,
             is_hero: bool = False) -> dict:
    return ctx.add("incidents", dict(incident_id=incident_id, system=system, started_at_utc=started, ended_at_utc=ended,
                                     description=description, affected_count=affected_count, available_at=ended,
                                     is_hero=is_hero))


def config_change(ctx: Ctx, change_id: str, system: str, changed_at: str, description: str, reverted_at: str = "",
                  is_hero: bool = False) -> dict:
    return ctx.add("config_changes", dict(change_id=change_id, system=system, changed_at_utc=changed_at,
                                          description=description, reverted_at_utc=reverted_at, available_at=changed_at,
                                          is_hero=is_hero))


def coaching(ctx: Ctx, coaching_id: str, colleague_id: str, created_at: str, source: str, topic: str,
             related_interaction_id: str = "", is_hero: bool = False) -> dict:
    return ctx.add("coaching_records", dict(coaching_id=coaching_id, colleague_id=colleague_id, created_at=created_at,
                                            source=source, topic=topic, related_interaction_id=related_interaction_id,
                                            available_at=created_at, is_hero=is_hero))


# ---------------------------------------------------------------- on-request artifacts (harness-gated)
def retranscription(ctx: Ctx, rtx_id: str, inter: dict, transcript: Transcript, *, segment: Optional[list] = None,
                    delay_hours: int = 4, method: str = "stereo channel-separated, human-verified") -> dict:
    data = transcript.data()
    data.update(retranscription_id=rtx_id, source="retranscription", method=method, requested_segment=segment)
    ctx.on_request["retranscriptions"][rtx_id] = data
    ctx.on_request_log.append(dict(artifact_id=rtx_id, kind="retranscription", interaction_id=inter["interaction_id"],
                                   release="request_time_plus_hours", delay_hours=delay_hours))
    return data


def audio_recovery(ctx: Ctx, aud_id: str, inter: dict, *, status: str, available_at: str, transcript_ref: str = "",
                   note: str = "") -> dict:
    data = dict(audio_recovery_id=aud_id, interaction_id=inter["interaction_id"], status=status,
                transcript_ref=transcript_ref, note=note, available_at=available_at)
    ctx.on_request["audio_recovery"][aud_id] = data
    ctx.on_request_log.append(dict(artifact_id=aud_id, kind="audio_recovery", interaction_id=inter["interaction_id"],
                                   release="fixed_available_at", available_at=available_at))
    return data


def colleague_statement(ctx: Ctx, cst_id: str, inter: dict, text: str, *, delay_business_days: int = 1) -> dict:
    data = dict(statement_id=cst_id, interaction_id=inter["interaction_id"], colleague_id=inter["colleague_id"],
                text=text)
    ctx.on_request["colleague_statements"][cst_id] = data
    ctx.on_request_log.append(dict(artifact_id=cst_id, kind="colleague_statement", interaction_id=inter["interaction_id"],
                                   release="request_time_plus_business_days", delay_business_days=delay_business_days))
    return data
