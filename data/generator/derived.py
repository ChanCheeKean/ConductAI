"""Deterministic arithmetic and time helpers.

The generator computes ground truth with these functions, the validator re-derives it with them, and the
implementation session ports them into sandbox helpers. Pure functions over plain values; no Ctx access.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from decimal import Decimal
from typing import Iterable, Sequence

from common import d, iso_utc, local_to_utc, money, parse_utc, utc_to_local

# US bank holidays (Federal Reserve schedule). 2026-07-04 falls on a Saturday: no weekday closure.
BANK_HOLIDAYS = {
    "2025-11-11": "Veterans Day", "2025-11-27": "Thanksgiving Day", "2025-12-25": "Christmas Day",
    "2026-01-01": "New Year's Day", "2026-01-19": "Birthday of Martin Luther King, Jr.",
    "2026-02-16": "Washington's Birthday", "2026-05-25": "Memorial Day", "2026-06-19": "Juneteenth National Independence Day",
    "2026-09-07": "Labor Day", "2026-10-12": "Columbus Day", "2026-11-11": "Veterans Day",
    "2026-11-26": "Thanksgiving Day", "2026-12-25": "Christmas Day", "2027-01-01": "New Year's Day",
}
_HOLIDAYS = {d(x) for x in BANK_HOLIDAYS}
MONITORING_SLA_BUSINESS_DAYS = 10     # CLB-SOP-CRM-001@v5 §4.1
DISCLOSURE_WPM_LIMIT = 220            # CLB-SOP-SAL-001@v4 §5.3
PROGRAM_EARLY_CANCEL_BASELINE = 0.11  # add-on cancellations within 30 days, program-wide assumption


# ---------------------------------------------------------------- business days
def is_business_day(day: dt.date) -> bool:
    return day.weekday() < 5 and day not in _HOLIDAYS


def add_business_days(start: str, n: int) -> str:
    """Move n business days after `start` (the start day itself is never counted)."""
    cur, k, step = d(start), 0, (1 if n >= 0 else -1)
    while k < abs(n):
        cur += dt.timedelta(days=step)
        if is_business_day(cur):
            k += 1
    return cur.isoformat()


def business_days_between(start: str, end: str) -> int:
    """Business days in (start, end]."""
    cur, n = d(start), 0
    while cur < d(end):
        cur += dt.timedelta(days=1)
        n += is_business_day(cur)
    return n


def latest_safe_decision(interaction_date: str, trigger_date: str, business_days: int = MONITORING_SLA_BUSINESS_DAYS) -> str:
    """CRM-001@v5 §4.1: N business days after the later of the interaction date and the selection/trigger date."""
    return add_business_days(max(interaction_date[:10], trigger_date[:10]), business_days)


# ---------------------------------------------------------------- clocks and time zones
def local_str_to_utc(ts_local: str, tz: str) -> str:
    """'2026-11-09T14:32:10' in tz -> ISO UTC."""
    date_s, time_s = ts_local.split("T")
    return local_to_utc(date_s, time_s, tz)


def desktop_true_utc(ts_local: str, tz: str, offset_seconds: int) -> str:
    """Workstation clock reading -> true UTC. A +9 s offset means the workstation clock runs 9 s fast."""
    return iso_utc(parse_utc(local_str_to_utc(ts_local, tz)) - dt.timedelta(seconds=offset_seconds))


def desktop_reading(true_utc: str, tz: str, offset_seconds: int) -> str:
    """True UTC -> what a workstation with this offset records (local wall time)."""
    return utc_to_local(iso_utc(parse_utc(true_utc) + dt.timedelta(seconds=offset_seconds)), tz)


def call_offset_to_utc(started_at_utc: str, offset_s: float) -> str:
    return iso_utc(parse_utc(started_at_utc) + dt.timedelta(seconds=round(offset_s)))


def seconds_between(a_utc: str, b_utc: str) -> int:
    """b - a in whole seconds."""
    return int((parse_utc(b_utc) - parse_utc(a_utc)).total_seconds())


def hms(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------- speech
def words_per_minute(words: Sequence[dict]) -> float:
    """Words per minute from word timings: word count / (last end - first start). Rounded to 0.1."""
    if not words:
        return 0.0
    span = words[-1]["end_s"] - words[0]["start_s"]
    return round(len(words) / span * 60, 1) if span > 0 else 0.0


def turn_wpm(turn: dict) -> float:
    return words_per_minute(turn["words"])


def median_wpm(turns: Iterable[dict]) -> float:
    rates = [turn_wpm(t) for t in turns if len(t.get("words") or []) >= 5]
    return round(statistics.median(rates), 1) if rates else 0.0


def overlaps(a: Sequence[float], b: Sequence[float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def in_any_gap(offset_s: float, gaps: Sequence[Sequence[float]]) -> bool:
    return any(g[0] <= offset_s < g[1] for g in gaps)


# ---------------------------------------------------------------- fees and rewards
def pct_fee(amount, rate_pct) -> Decimal:
    """Fee = amount × rate% rounded half-up to the cent. pct_fee(1850, '1.72') -> 31.82."""
    return money(Decimal(str(amount)) * Decimal(str(rate_pct)) / Decimal(100))


def cardshield_premium(ending_balance) -> Decimal:
    """CLB-PRD-CARDSHIELD@v3 §2.1: $0.89 per $100 of the ending statement balance (zero if balance <= 0)."""
    bal = Decimal(str(ending_balance))
    return money(bal * Decimal("0.89") / Decimal(100)) if bal > 0 else money(0)


def miles_to_cash(miles: int, cents_per_mile="0.5") -> Decimal:
    """CLB-PRD-VOYAGER@v5 §5: product change conversion. miles_to_cash(48200) -> 241.00."""
    return money(Decimal(miles) * Decimal(str(cents_per_mile)) / Decimal(100))


def refund_window_end(fee_posted: str, days: int = 30) -> str:
    """Cardholder agreement §6.1: annual fee refunded if closed within `days` of posting (inclusive end date)."""
    return (d(fee_posted) + dt.timedelta(days=days)).isoformat()


# ---------------------------------------------------------------- credit line policy
def cli_inquiry_type(policy_version: str, tenure_months: int, increase: int) -> str:
    """CLB-POL-CLI: v5 always SOFT; v6 HARD if tenure < 12 months or increase > $5,000."""
    if policy_version == "v5":
        return "SOFT"
    return "HARD" if tenure_months < 12 or increase > 5000 else "SOFT"


def cli_policy_version(interaction_date: str) -> str:
    return "v6" if interaction_date[:10] >= "2026-10-01" else "v5"


def tenure_months(customer_since: str, on_date: str) -> int:
    a, b = d(customer_since), d(on_date)
    months = (b.year - a.year) * 12 + (b.month - a.month)
    return months - (1 if b.day < a.day else 0)


# ---------------------------------------------------------------- statistics
def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def binomial_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p): one-sided exact test p-value."""
    return min(1.0, sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def colleague_cancel_stats(rows: Iterable[tuple], min_enrollments: int = 10) -> dict:
    """rows: (colleague_id, enrollments, cancelled_within_30d). Returns per-colleague rates and program mean/sd
    over colleagues with >= min_enrollments."""
    per = {c: dict(enrollments=n, cancelled=k, rate=rate(k, n)) for c, n, k in rows}
    eligible = {c: v for c, v in per.items() if v["enrollments"] >= min_enrollments}
    rates = [v["rate"] for v in eligible.values()]
    mean = round(statistics.mean(rates), 4) if rates else 0.0
    sd = round(statistics.pstdev(rates), 4) if len(rates) > 1 else 0.0
    top = max(eligible, key=lambda c: (eligible[c]["rate"], c)) if eligible else None
    return dict(per_colleague=per, eligible=sorted(eligible), mean=mean, sd=sd, highest=top)


def precision_recall(pred: Iterable[bool], gold: Iterable[bool]) -> dict:
    tp = fp = fn = tn = 0
    for p, g in zip(pred, gold):
        tp += p and g
        fp += p and not g
        fn += (not p) and g
        tn += (not p) and (not g)
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=rate(tp, tp + fp), recall=rate(tp, tp + fn),
                fp_rate=rate(fp, fp + tn))
