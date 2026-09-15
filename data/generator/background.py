"""Generate 6,500 non-hero interactions with realistic channel and label mixes."""
from __future__ import annotations

import datetime as dt

import asr_noise
import people
import records as R
import world
from common import Ctx, add_seconds, sub_rng
from heroes.kit import label
from transcripts import Transcript

TARGET = 6500
CHANNELS = (["phone"] * 68) + (["chat"] * 24) + (["secure_message"] * 8)
INTENTS = (["balance_payment"] * 22 + ["fee_question"] * 14 + ["lost_card"] * 11 + ["rewards"] * 8 +
           ["product_question"] * 8 + ["credit_line_increase"] * 7 + ["balance_transfer"] * 6 +
           ["close_account"] * 5 + ["hardship"] * 4 + ["dispute"] * 4 + ["address_profile"] * 6 + ["other"] * 5)
DISP = {"balance_payment":"BALANCE_PAYMENT","fee_question":"FEE_INQUIRY","lost_card":"CARD_REPLACEMENT",
        "rewards":"REWARDS","product_question":"PRODUCT_INFO","credit_line_increase":"CLI_REQUEST",
        "balance_transfer":"SALE_BT","close_account":"RETENTION_SAVE","hardship":"HARDSHIP",
        "dispute":"DISPUTE_INTAKE","address_profile":"PROFILE_UPDATE","other":"GEN_INQUIRY"}
CATEGORIES = (["MC-02"]*24+["MC-03"]*18+["MC-04"]*16+["MC-06"]*10+["MC-05"]*8+["MC-01"]*7+
              ["MC-10"]*6+["MC-09"]*4+["MC-11"]*4+["MC-07"]*2+["MC-08"])


def _date(i: int) -> str:
    if i < 500:
        return (dt.date(2026,11,9) + dt.timedelta(days=i % 5)).isoformat()
    return (dt.date(2026,8,17) + dt.timedelta(days=(i * 17) % 84)).isoformat()


def _lines(intent: str, positive: bool, cat: str, language: str) -> list[tuple[str,str]]:
    if language == "es":
        return [("colleague","Gracias por llamar a Copperlake. Voy a verificar su cuenta."),("customer","Necesito ayuda con mi tarjeta."),
                ("colleague","Claro, revisemos las opciones."),("customer","Sí, gracias."),("colleague","¿Hay algo más en que le ayude?")]
    need={"balance_payment":"I have a question about my balance and payment.","fee_question":"Can you explain this fee?",
          "lost_card":"My card is missing and I need a replacement.","rewards":"How many rewards do I have?",
          "product_question":"Could you explain the card benefits?","credit_line_increase":"I'd like a higher credit line.",
          "balance_transfer":"Do I have a balance transfer offer?","close_account":"I am thinking about closing the account.",
          "hardship":"My income dropped and I need payment help.","dispute":"I don't recognize a charge.",
          "address_profile":"I need to update my address.","other":"I have a general account question."}[intent]
    normal="I've completed the request and reviewed the applicable terms with you."
    bad={"MC-01":"You already said no, but you really need to take this offer today.",
         "MC-02":"I'm adding CardShield for you now, okay?","MC-03":"This protection is basically free if you pay on time.",
         "MC-04":"The details are standard and we can skip the price.","MC-05":"This request can never affect your credit score.",
         "MC-06":"I can waive that fee only if you add protection.","MC-07":"This is a servicing call, but I'm enrolling you in an offer.",
         "MC-08":"I switched your card; the details do not matter.","MC-09":"Even with hardship active, this new credit plan will help.",
         "MC-10":"You do not have the right to file that complaint.","MC-11":"I'll mark this as a general inquiry even though you complained."}
    reply="Okay." if positive and cat in ("MC-02","MC-06") else "Thank you."
    return [("colleague","Thank you for calling Copperlake. I need to verify your account."),("customer",need),
            ("colleague",bad[cat] if positive else normal),("customer",reply),("colleague","Is there anything else I can help with today?")]


def build(ctx: Ctx):
    rng=sub_rng("background")
    existing=[x for x in ctx.t["interactions"] if not x["is_hero"]]
    missing=TARGET-len(existing)
    existing_mis=sum(v["gold_status"]=="misconduct" and v.get("source")!="hero" for v in ctx.bg_labels.values())
    positive_needed=round(TARGET*.036)-existing_mis
    positive_slots=set(rng.sample(range(missing),positive_needed))
    bg_customers=[c for c in ctx.t["customers"] if not c["is_hero"]]
    agents=[c["colleague_id"] for c in ctx.t["colleagues"] if c["role"]=="agent" and c["colleague_id"] not in ("COL-4421","COL-4425")]
    existing_ids=set(ctx.index["interactions"])
    for i in range(missing):
        iid=R.opaque_id(ctx,"INT","interactions","background",i)
        cust=bg_customers[(i*37)%len(bg_customers)]; acct=ctx.get("accounts",cust["customer_id"].replace("CUS","ACC"))
        channel=CHANNELS[i%100]; intent=INTENTS[(i*29)%100]; positive=i in positive_slots
        cat=CATEGORIES[(i*31)%100] if positive else ""
        col=agents[(i*13)%len(agents)]; day=_date(i)
        bilingual=channel=="phone" and i%100<9
        language="es" if bilingual and i%20<5 else "en"
        if channel=="phone":
            swap=i%50==0
            tr=asr_noise.call(iid,_lines(intent,positive,cat,language),sub_rng("asr",i),language=language,swap=swap,wpm=145+(i%45))
        else:
            tr=Transcript(iid,channel,language=language)
            for speaker,text in _lines(intent,positive,cat,language): tr.message(speaker,text)
        direction="outbound" if channel=="phone" and i%100<9 else "inbound"
        queue="bilingual" if bilingual else "general"
        start=f"{day}T{8+(i%11):02d}:{(i*7)%60:02d}:00"
        inter=R.interaction(ctx,iid,cust=cust,acct=acct,colleague_id=col,channel=channel,start_local=start,
                           tz=world.site_tz(col),transcript=tr,disposition=DISP[intent],direction=direction,
                           outbound_reason="servicing_followup" if direction=="outbound" else "none",queue=queue,
                           ivr_intent=intent,is_hero=False)
        for seq,(offset,event_type) in enumerate(((1,"profile_loaded"),(2,"authentication_started"),(3,"authentication_completed"),(4,"account_summary_opened"),(5,"disposition_selected"))):
            R.desktop(ctx,inter,min(offset,max(0,tr.end_s-.2)),event_type,{"intent":intent},seq=50+seq)
        if channel=="phone":
            R.ievent(ctx,inter,"authentication",1,min(8,tr.end_s),{"status":"completed"})
            R.ievent(ctx,inter,"conversation",min(8,tr.end_s),tr.end_s,{"language":language})
        R.crm_note(ctx,inter,f"Handled {intent.replace('_',' ')} request; disposition {DISP[intent]}.")
        if i%100==0:
            R.complaint(ctx,R.opaque_id(ctx,"COMP","complaints","background",i),cust,inter["ended_at_utc"],channel,
                        logged_by=col,related_interaction_ids=[iid],category="service_dissatisfaction",
                        text="Customer expressed dissatisfaction and requested follow-up.")
        # About 28% carry a sale opportunity; keep cancellation rates well below C11.
        if i%100<28:
            R.desktop(ctx,inter,max(2,tr.end_s-3),"offer_displayed",{"offer_code":"OFR-ADDON-CS"})
        if i%100<12:
            cancelled=sub_rng("background-cancel",i).random()<.11
            R.enrollment(ctx,R.opaque_id(ctx,"ENR","enrollments","background",i),acct,"CARDSHIELD",inter,max(3,tr.end_s-2),
                         status="cancelled" if cancelled else "active",
                         cancelled_at=add_seconds(inter["ended_at_utc"],864000) if cancelled else "",
                         cancel_reason="customer_request" if cancelled else "",cancel_channel=channel if cancelled else "")
        if intent=="balance_transfer" and i%2==0:
            R.offer(ctx,R.opaque_id(ctx,"OFRI","offers","background",i),inter,acct,"OFR-BT-12-3","BT",
                    presented_offset=3,accepted=True,submitted_offset=max(5,tr.end_s-1),amount=1200,fee_rate="3.00",
                    fee_amount=36,promo_apr="0.00",promo_months=12)
        label(ctx,iid,"misconduct" if positive else "no_error",[cat] if positive else [],
              attributable_to="colleague" if positive else "none",customer_harm=positive,
              is_bright_line=cat in ("MC-02","MC-03","MC-04","MC-05","MC-07","MC-08","MC-11") if positive else None,
              source="background")
    ctx.planted["background"]={"target_interactions":TARGET,"gold_misconduct":round(TARGET*.036),
                               "channel_targets":{"phone":.68,"chat":.24,"secure_message":.08}}
