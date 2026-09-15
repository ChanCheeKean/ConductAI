"""Background customer pool: customers, accounts and monthly statements.

Built before heroes so planted populations and the background generator draw from the same people.
"""
from __future__ import annotations

import datetime as dt
import random
from typing import Callable, Optional

import records as R
import world
from common import Ctx, add_days, d, m, sub_rng

N_BACKGROUND_CUSTOMERS = 1150
PRODUCT_WEIGHTS = {"EVERYDAY_CASH": 45, "VOYAGER": 30, "SUMMIT": 8, "FOUNDATION": 17}
LIMITS = {"EVERYDAY_CASH": (1500, 12000), "VOYAGER": (4000, 20000), "SUMMIT": (10000, 35000), "FOUNDATION": (300, 1500)}
STATEMENT_MONTHS = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
SPANISH_SHARE = 0.08


def _since(rng: random.Random) -> str:
    """Tenure mix: ~12% under 12 months at AS_OF, long tail back to 1999."""
    if rng.random() < 0.12:
        return (d("2025-11-20") + dt.timedelta(days=rng.randint(0, 300))).isoformat()
    return (d("1999-01-04") + dt.timedelta(days=rng.randint(0, 9400))).isoformat()


def _statement_dates(month: str, closing_day: int) -> tuple:
    end = f"{month}-{closing_day:02d}"
    prev = (d(end).replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    return add_days(f"{prev}-{closing_day:02d}", 1), end


def statements_for(ctx: Ctx, acct: dict, rng: random.Random, *, through: str = "2026-11-15"):
    """Monthly statements for STATEMENT_MONTHS whose period ends on or before `through`."""
    limit = int(acct["credit_limit"])
    typical = rng.uniform(0.05, 0.55) * limit
    for month in STATEMENT_MONTHS:
        start, end = _statement_dates(month, int(acct["statement_closing_day"]))
        if end > through or end < acct["opened_at"]:
            continue
        bal = max(0.0, rng.gauss(typical, typical * 0.25)) if rng.random() > 0.04 else 0.0
        R.statement(ctx, f"STM-{R.num(acct['account_id'])}-{month.replace('-', '')}", acct, start, end, m(bal),
                    is_hero=acct["is_hero"])


def build(ctx: Ctx):
    rng = sub_rng("people")
    cities = [c[0] for c in world.CITIES]
    weights = [c[5] for c in world.CITIES]
    products, pweights = list(PRODUCT_WEIGHTS), list(PRODUCT_WEIGHTS.values())
    for i in range(1, N_BACKGROUND_CUSTOMERS + 1):
        cid = f"CUS-{i:05d}"
        city = rng.choices(cities, weights)[0]
        spanish = rng.random() < (SPANISH_SHARE * (2.2 if city in ("San Antonio", "El Paso", "Houston", "Albuquerque",
                                                                     "Phoenix", "Tucson", "Mesa") else 0.5))
        first = rng.choice(world.FIRST_NAMES_ES if spanish else world.FIRST_NAMES)
        last = rng.choice(world.LAST_NAMES_ES if spanish or rng.random() < 0.1 else world.LAST_NAMES)
        since = _since(rng)
        cust = R.customer(ctx, cid, first, last, city, birth_year=rng.randint(1941, 2004), since=since,
                          language="es" if spanish else "en", trusted_contact=rng.random() < 0.07,
                          military="scra_active" if rng.random() < 0.01 else "none")
        product = rng.choices(products, pweights)[0]
        lo, hi = LIMITS[product]
        rewards = rng.randint(0, 90000) if world.PRODUCTS[product]["rewards_unit"] == "miles" else rng.randint(0, 600)
        acct = R.account(ctx, f"ACC-{i:05d}", cust, product, opened=since, credit_limit=rng.randrange(lo, hi, 100),
                         rewards_balance=rewards, statement_closing_day=rng.choice([3, 8, 12, 17, 20, 25]))
        statements_for(ctx, acct, rng)


def pick(ctx: Ctx, rng: random.Random, *, where: Optional[Callable[[dict, dict], bool]] = None,
         exclude: Optional[set] = None) -> tuple:
    """Pick a background (customer, account) pair satisfying `where(cust, acct)`, excluding customer IDs in `exclude`."""
    pool = [(ctx.get("customers", a["customer_id"]), a) for a in ctx.t["accounts"] if not a["is_hero"]]
    pool = [(c, a) for c, a in pool if (not exclude or c["customer_id"] not in exclude) and (not where or where(c, a))]
    if not pool:
        raise LookupError("no background customer matches the filter")
    return rng.choice(pool)


def latest_statement(ctx: Ctx, account_id: str, on_or_before: str) -> Optional[dict]:
    rows = [s for s in ctx.t["statements"] if s["account_id"] == account_id and s["period_end"] <= on_or_before]
    return max(rows, key=lambda s: s["period_end"]) if rows else None
