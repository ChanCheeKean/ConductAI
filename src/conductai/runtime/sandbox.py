"""Registered deterministic sandbox helpers ported from data/generator/derived.py."""

from __future__ import annotations

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
