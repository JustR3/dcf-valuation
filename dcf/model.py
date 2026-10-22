"""Pure DCF math: growth paths, discounting, equity/FCFF per-share value, reverse solve.

No I/O and no network. All rates are decimals (0.05 = 5%). Money units only need to be
consistent (for example millions for cash flows and net debt, millions for shares).
User-input violations raise ValueError.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from scipy.optimize import brentq

Model = Literal["equity", "fcff"]

G_LOWER = -0.50
G_UPPER = 1.00
MAX_YEARS = 30
GRID_R_OFFSETS = (-0.02, -0.01, 0.0, 0.01, 0.02)
GRID_TERMINAL_GROWTHS = (0.015, 0.025, 0.035)


@dataclass(frozen=True)
class YearRow:
    """One explicit forecast year."""

    year: int
    growth: float
    cash_flow: float
    pv: float


@dataclass(frozen=True)
class ValueBreakdown:
    """Result of `discount`. terminal_share = terminal_pv / total_pv."""

    explicit_pv: float
    terminal_pv: float
    total_pv: float
    terminal_share: float
    rows: tuple[YearRow, ...]


@dataclass(frozen=True)
class ImpliedResult:
    """Result of `implied_growth`.

    status "ok": `growth` is the root.
    status "below_lower": price is below the value at the lower bound; `bound` = lower bound.
    status "above_upper": price is above the value at the upper bound; `bound` = upper bound.
    status "invalid": the inputs cannot be valued (grid cell with r <= g_T).
    """

    status: Literal["ok", "below_lower", "above_upper", "invalid"]
    growth: float | None = None
    bound: float | None = None


def _finite(**values: float) -> None:
    for name, v in values.items():
        if not isinstance(v, int | float) or not math.isfinite(v):
            raise ValueError(f"{name} must be a finite number, got {v!r}")


def _check_years(years: int) -> None:
    if not isinstance(years, int) or isinstance(years, bool) or not 1 <= years <= MAX_YEARS:
        raise ValueError(f"years must be an integer from 1 to {MAX_YEARS}, got {years!r}")


def _check_tax(tax_rate: float) -> None:
    _finite(tax_rate=tax_rate)
    if not 0.0 <= tax_rate < 1.0:
        raise ValueError(f"tax_rate must satisfy 0 <= tax < 1, got {tax_rate}")


def growth_path(g: float, g_t: float, years: int, fade: bool) -> list[float]:
    """Growth rate for each year t = 1..years.

    Constant: g every year. Fade: g_t_ = g + (g_t - g) * (t - 1) / (years - 1), so the first
    element is g and the last is g_t; for years == 1 the path is [g].
    """
    _finite(g=g, g_t=g_t)
    _check_years(years)
    if not fade or years == 1:
        return [float(g)] * years
    return [g + (g_t - g) * (t - 1) / (years - 1) for t in range(1, years + 1)]


def discount(base_cf: float, path: Sequence[float], r: float, g_t: float) -> ValueBreakdown:
    """Discount a cash-flow stream grown along `path` and add a Gordon terminal value.

    CF_t = CF_{t-1} * (1 + path[t-1]); TV_N = CF_N * (1 + g_t) / (r - g_t);
    PV = sum CF_t / (1+r)^t + TV_N / (1+r)^N. No terminal-value cap.
    Requires finite inputs, base_cf > 0, r > g_t, 1 <= len(path) <= 30.
    """
    _finite(base_cf=base_cf, r=r, g_t=g_t)
    if base_cf <= 0:
        raise ValueError(f"base cash flow must be positive, got {base_cf}")
    if r <= g_t:
        raise ValueError(f"discount rate ({r}) must exceed terminal growth ({g_t})")
    _check_years(len(path))
    rows = []
    cf = float(base_cf)
    explicit = 0.0
    for t, g in enumerate(path, start=1):
        _finite(growth=g)
        cf *= 1.0 + g
        pv = cf / (1.0 + r) ** t
        explicit += pv
        rows.append(YearRow(year=t, growth=float(g), cash_flow=cf, pv=pv))
    n = len(path)
    terminal_pv = cf * (1.0 + g_t) / (r - g_t) / (1.0 + r) ** n
    total = explicit + terminal_pv
    assert math.isfinite(total), "non-finite PV"
    return ValueBreakdown(
        explicit_pv=explicit,
        terminal_pv=terminal_pv,
        total_pv=total,
        terminal_share=terminal_pv / total,
        rows=tuple(rows),
    )


def fcff_base(levered_fcf: float, interest: float, tax_rate: float) -> float:
    """FCFF base = levered FCF + interest * (1 - tax_rate)."""
    _finite(levered_fcf=levered_fcf, interest=interest)
    _check_tax(tax_rate)
    return levered_fcf + interest * (1.0 - tax_rate)


def wacc(e: float, d: float, ke: float, kd: float, tax_rate: float) -> float:
    """WACC = E/(D+E) * ke + D/(D+E) * kd * (1 - tax_rate). e, d are market/book values."""
    _finite(e=e, d=d, ke=ke, kd=kd)
    _check_tax(tax_rate)
    if e < 0 or d < 0 or e + d <= 0:
        raise ValueError(f"e and d must be non-negative with e + d > 0, got e={e}, d={d}")
    total = e + d
    return e / total * ke + d / total * kd * (1.0 - tax_rate)


def per_share(
    base_cf: float,
    g: float,
    r: float,
    g_t: float,
    years: int,
    shares: float,
    model: Model = "equity",
    fade: bool = False,
    net_debt: float = 0.0,
) -> float:
    """Value per share.

    model "equity": PV / shares (r = cost of equity, base_cf = levered FCF).
    model "fcff": (PV - net_debt) / shares (r = WACC, base_cf = FCFF base).
    May be negative in fcff mode when net debt is large.
    """
    _finite(shares=shares, net_debt=net_debt)
    if shares <= 0:
        raise ValueError(f"shares must be positive, got {shares}")
    if model not in ("equity", "fcff"):
        raise ValueError(f"model must be 'equity' or 'fcff', got {model!r}")
    pv = discount(base_cf, growth_path(g, g_t, years, fade), r, g_t).total_pv
    debt = net_debt if model == "fcff" else 0.0
    return (pv - debt) / shares


def implied_growth(
    price: float,
    base_cf: float,
    r: float,
    g_t: float,
    years: int,
    shares: float,
    model: Model = "equity",
    fade: bool = False,
    net_debt: float = 0.0,
) -> ImpliedResult:
    """Solve per_share(g) == price for g in [-50%, +100%] with brentq.

    per_share is strictly increasing in g, so the root is unique. If price lies outside
    [per_share(-50%), per_share(+100%)], return status "below_lower" or "above_upper" with the
    failing bound. No extrapolation. With fade=True, g is the starting growth rate.
    """
    _finite(price=price)

    def f(g: float) -> float:
        return per_share(base_cf, g, r, g_t, years, shares, model, fade, net_debt) - price

    f_lo = f(G_LOWER)
    f_hi = f(G_UPPER)
    if f_lo > 0:
        return ImpliedResult(status="below_lower", bound=G_LOWER)
    if f_hi < 0:
        return ImpliedResult(status="above_upper", bound=G_UPPER)
    if f_lo == 0:
        return ImpliedResult(status="ok", growth=G_LOWER)
    if f_hi == 0:
        return ImpliedResult(status="ok", growth=G_UPPER)
    root = brentq(f, G_LOWER, G_UPPER, xtol=1e-13, rtol=1e-14, maxiter=500)
    return ImpliedResult(status="ok", growth=float(root))


def grid(
    price: float,
    base_cf: float,
    r: float,
    years: int,
    shares: float,
    model: Model = "equity",
    fade: bool = False,
    net_debt: float = 0.0,
    r_offsets: Sequence[float] = GRID_R_OFFSETS,
    terminal_growths: Sequence[float] = GRID_TERMINAL_GROWTHS,
) -> dict[tuple[float, float], ImpliedResult]:
    """Implied growth for each (r offset, terminal growth) pair, keyed (offset, g_t).

    Offsets are decimals added to r (default -2, -1, 0, +1, +2 pp); terminal growths default to
    1.5%, 2.5%, 3.5%. A cell with r + offset <= g_t is reported as status "invalid".
    """
    _finite(r=r)
    out: dict[tuple[float, float], ImpliedResult] = {}
    for off in r_offsets:
        for g_t in terminal_growths:
            r_cell = r + off
            if r_cell <= g_t:
                out[(off, g_t)] = ImpliedResult(status="invalid")
            else:
                out[(off, g_t)] = implied_growth(price, base_cf, r_cell, g_t, years, shares, model, fade, net_debt)
    return out
