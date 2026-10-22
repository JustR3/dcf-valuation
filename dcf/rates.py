"""Risk-free rate (FRED DGS10), cost of equity, and the discount rate (Ke or WACC)."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date

import requests

from dcf.errors import DCFInputError
from dcf.model import wacc

ERP_DEFAULT = 0.05
KD_SPREAD = 0.015
TAX_FALLBACK = 0.21
TAX_MAX = 0.99
FRED_MAX_AGE_DAYS = 10
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES = "DGS10"
FRED_TIMEOUT_S = 20


class StaleRate(DCFInputError):  # noqa: N818
    """The latest FRED observation is older than the freshness limit."""


class MissingSecret(DCFInputError):  # noqa: N818
    """A required secret (env var) is not set."""


@dataclass(frozen=True)
class RiskFree:
    rate: float
    obs_date: date
    source: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RateBreakdown:
    model: str
    rate: float
    ke: float
    kd: float | None
    tax_rate: float | None
    weight_equity: float | None
    weight_debt: float | None
    warnings: tuple[str, ...] = ()


def fred_fetch(api_key: str, series: str = FRED_SERIES) -> dict:
    """Fetch the latest observations of a FRED series (newest first)."""
    resp = requests.get(
        FRED_URL,
        params={
            "series_id": series,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10,
        },
        timeout=FRED_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


def require_fred_key(env: Mapping[str, str] = os.environ) -> str:
    key = (env.get("FRED_API_KEY") or "").strip()
    if not key:
        raise MissingSecret(
            "FRED_API_KEY is not set. Add it to .env (see .env.example) or pass --rf."
        )
    return key


def risk_free(
    api_key: str,
    fetch: Callable[..., dict] = fred_fetch,
    today: date | None = None,
    allow_stale: bool = False,
) -> RiskFree:
    today = today or date.today()
    payload = fetch(api_key, FRED_SERIES)
    latest = None
    for row in payload.get("observations", []):
        value = str(row.get("value", ".")).strip()
        if value in ("", "."):
            continue
        d = date.fromisoformat(row["date"])
        pct = float(value)
        if not math.isfinite(pct):
            continue
        if latest is None or d > latest[0]:
            latest = (d, pct)
    if latest is None:
        raise StaleRate(f"FRED {FRED_SERIES} returned no valid observation.")
    obs_date, pct = latest
    age = (today - obs_date).days
    warnings: tuple[str, ...] = ()
    if age > FRED_MAX_AGE_DAYS:
        msg = (
            f"FRED {FRED_SERIES} latest observation is {obs_date.isoformat()} "
            f"({age} days old, limit {FRED_MAX_AGE_DAYS})."
        )
        if not allow_stale:
            raise StaleRate(msg + " Pass --allow-stale to continue or --rf to override.")
        warnings = (msg,)
    return RiskFree(pct / 100.0, obs_date, f"FRED {FRED_SERIES}", warnings)


def cost_of_equity(rf: float, beta: float, erp: float = ERP_DEFAULT) -> float:
    return rf + beta * erp


def _missing(x: float | None) -> bool:
    return x is None or not math.isfinite(x)


def fcff_tax_rate(
    ttm_tax_provision: float | None,
    ttm_pretax_income: float | None,
    override: float | None = None,
) -> tuple[float, tuple[str, ...]]:
    """Effective tax rate for FCFF and WACC, with warnings. Use it for both the base and WACC."""
    if override is not None:
        return override, ()
    if _missing(ttm_tax_provision) or _missing(ttm_pretax_income) or ttm_pretax_income <= 0:
        return TAX_FALLBACK, (
            f"Tax rate unavailable (missing data or pretax income <= 0): "
            f"using {TAX_FALLBACK:.0%} fallback.",
        )
    t = ttm_tax_provision / ttm_pretax_income
    if t < 0 or t > TAX_MAX:
        clipped = min(max(t, 0.0), TAX_MAX)
        return clipped, (f"Computed tax rate {t:.1%} clipped to {clipped:.0%}.",)
    return t, ()


def discount_rate(
    model: str,
    rf: float,
    beta: float,
    erp: float,
    price: float,
    shares: float,
    total_debt: float | None,
    ttm_interest: float | None,
    ttm_tax_provision: float | None,
    ttm_pretax_income: float | None,
    override: float | None = None,
    tax_override: float | None = None,
    kd_override: float | None = None,
) -> RateBreakdown:
    if model not in ("equity", "fcff"):
        raise ValueError(f"model must be 'equity' or 'fcff', got {model!r}")
    ke = cost_of_equity(rf, beta, erp)
    warnings: list[str] = []

    if model == "equity":
        rate = ke
        kd = tax = we = wd = None
    else:
        if _missing(total_debt):
            raise ValueError("total_debt is required for the fcff model")
        tax, tax_w = fcff_tax_rate(ttm_tax_provision, ttm_pretax_income, tax_override)
        warnings.extend(tax_w)
        if kd_override is not None:
            kd = kd_override
        elif _missing(ttm_interest) or total_debt == 0:
            kd = rf + KD_SPREAD
            warnings.append(
                f"Kd unavailable (interest missing or debt = 0): using rf + {KD_SPREAD:.1%}."
            )
        else:
            kd = ttm_interest / total_debt
        e = price * shares
        rate = wacc(e, total_debt, ke, kd, tax)
        we = e / (e + total_debt)
        wd = total_debt / (e + total_debt)

    if override is not None:
        warnings.append(
            f"Discount rate override {override:.2%} replaces computed {rate:.2%}."
        )
        rate = override
    return RateBreakdown(model, rate, ke, kd, tax, we, wd, tuple(warnings))
