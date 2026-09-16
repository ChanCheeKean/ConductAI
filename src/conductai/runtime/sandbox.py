"""Registered deterministic sandbox helpers ported from data/generator/derived.py."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo


def desktop_true_utc(ts_local: str, tz: str, offset_seconds: int) -> datetime:
    """Workstation clock reading -> true UTC. A positive offset means the workstation clock runs fast."""
    local = datetime.fromisoformat(ts_local).replace(tzinfo=ZoneInfo(tz))
    return local.astimezone(UTC) - timedelta(seconds=offset_seconds)


def pct_fee(amount: str, rate_pct: str) -> Decimal:
    """Fee = amount x rate% rounded half-up to the cent."""
    return (Decimal(amount) * Decimal(rate_pct) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def local_to_utc(ts_local: str, tz: str) -> datetime:
    """A system-of-record local timestamp with no clock skew -> true UTC."""
    return desktop_true_utc(ts_local, tz, 0)


def words_per_minute(words: list[dict]) -> float:
    """Words per minute from word timings: word count / (last end - first start). Rounded to 0.1."""
    if not words:
        return 0.0
    span = float(words[-1]["end_s"]) - float(words[0]["start_s"])
    return round(len(words) / span * 60, 1) if span > 0 else 0.0


def one_sided_binomial_upper_tail(n: int, k: int, p: float) -> float:
    """P(X >= k) under X ~ Binomial(n, p); the one-sided test for an observed-rate anomaly."""
    return sum(math.comb(n, i) * (p**i) * ((1 - p) ** (n - i)) for i in range(k, n + 1))
