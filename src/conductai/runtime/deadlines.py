"""Registered deterministic monitoring-deadline helpers."""

from __future__ import annotations

from datetime import date, timedelta


_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 9, 7), date(2026, 10, 12), date(2026, 11, 11),
    date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1),
}


def latest_safe_decision(interaction_date: str, trigger_date: str, business_days: int = 10) -> str:
    current = max(date.fromisoformat(interaction_date[:10]), date.fromisoformat(trigger_date[:10]))
    remaining = business_days
    while remaining:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in _HOLIDAYS:
            remaining -= 1
    return current.isoformat()
