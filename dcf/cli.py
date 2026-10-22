"""Command line interface: `dcf implied | value | grid`.

All percent flags are given in percent (6 = 6%). `--fcf` and `--shares` are given in millions.
Every refusal (DCFInputError, ValueError from inputs) prints one line on stderr and exits 2.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from dcf import model
from dcf.data import CompanyInputs, load_company, yf_fetch
from dcf.errors import EXIT_CODE, DCFInputError, MissingData
from dcf.rates import (
    ERP_DEFAULT,
    RateBreakdown,
    RiskFree,
    discount_rate,
    fred_fetch,
    require_fred_key,
    risk_free,
)

TERMINAL_GROWTH_DEFAULT = 0.025
YEARS_DEFAULT = 10
MILLION = 1e6

# Warnings from the data layer that only matter for the fcff model.
FCFF_ONLY_PREFIXES = (
    "TTM interest expense",
    "TTM tax provision",
    "TTM pretax income",
    "Total Debt missing",
    "Total Debt uses",
    "Cash missing",
    "Cash Cash Equivalents",
    "Cash And Cash Equivalents",
)
RF_NOT_USED = "not used"


# ------------------------------------------------------------------ parser

def _pct(x: float | None) -> float | None:
    return None if x is None else x / 100.0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("ticker", help="ticker symbol, for example KO")
    common.add_argument("--model", choices=("equity", "fcff"), default="equity",
                        help="cash-flow model (default: equity)")
    common.add_argument("--fade", action="store_true",
                        help="fade growth linearly to terminal growth instead of holding it constant")
    common.add_argument("--years", type=int, default=YEARS_DEFAULT,
                        help=f"explicit forecast years, 1-{model.MAX_YEARS} (default: {YEARS_DEFAULT})")
    common.add_argument("--erp", type=float, default=ERP_DEFAULT * 100,
                        help="equity risk premium in percent (default: 5.0)")
    common.add_argument("--beta", type=float, help="override beta (needed when yfinance has none)")
    common.add_argument("--rf", type=float, help="risk-free rate in percent; skips FRED")
    common.add_argument("--discount-rate", type=float, help="override the discount rate, in percent")
    common.add_argument("--tax-rate", type=float, help="fcff only: override the tax rate, in percent")
    common.add_argument("--kd", type=float, help="fcff only: override the pre-tax cost of debt, in percent")
    common.add_argument("--fcf", type=float, help="override base TTM free cash flow, in millions")
    common.add_argument("--shares", type=float, help="override shares outstanding, in millions")
    common.add_argument("--json", action="store_true", help="print JSON instead of text")
    common.add_argument("--force", action="store_true", help="run Financial Services companies anyway")
    common.add_argument("--allow-stale", action="store_true",
                        help="continue with stale data and print a warning")

    tg = argparse.ArgumentParser(add_help=False)
    tg.add_argument("--terminal-growth", type=float, default=TERMINAL_GROWTH_DEFAULT * 100,
                    help="terminal growth in percent (default: 2.5)")

    p = argparse.ArgumentParser(prog="dcf", description="Lean reverse DCF: what growth does the price imply?")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("implied", parents=[common, tg], help="solve for the growth the price implies")
    value = sub.add_parser("value", parents=[common, tg], help="value per share for a growth rate")
    value.add_argument("--growth", type=float, required=True, help="growth rate in percent (starting rate with --fade)")
    sub.add_parser("grid", parents=[common], help="implied growth for discount rate x terminal growth")
    return p


# ------------------------------------------------------------------ build report

def _inputs_block(
    c: CompanyInputs, args: argparse.Namespace, shares: float, base_fcf: float, rf: RiskFree,
    beta: float, beta_src: str, rb: RateBreakdown, years: int, g_t: float | None,
    erp: float, net_debt: float | None, base_cf: float, interest_added: float | None,
) -> dict:
    inputs: dict = {
        "price": {"value": c.price, "as_of": c.price_date, "source": "yfinance latest close (may be intraday)"},
        "balance_sheet_date": c.balance_sheet_date,
        "shares": {"value": shares, "source": "--shares" if args.shares is not None else c.shares_source},
        "levered_fcf": {
            "value": base_fcf,
            "as_of": c.latest_quarter_end,
            "source": "--fcf" if args.fcf is not None else c.fcf_source,
        },
        "risk_free": {"value": rf.rate, "as_of": rf.obs_date, "source": rf.source},
        "beta": {"value": beta, "source": beta_src},
        "erp": erp,
        "years": years,
        "terminal_growth": g_t,
        "base_cash_flow": base_cf,
    }
    if rb.model == "fcff":
        inputs["interest_added_after_tax"] = interest_added
        inputs["total_debt"] = {"value": c.total_debt, "source": "balance sheet: Total Debt (latest quarter)"}
        inputs["cash"] = {"value": c.cash, "source": c.cash_source}
        inputs["net_debt"] = net_debt
    return inputs


def _rate_block(rb: RateBreakdown, override: float | None) -> dict:
    return {
        "discount_rate": rb.rate,
        "cost_of_equity": rb.ke,
        "cost_of_debt": rb.kd,
        "tax_rate": rb.tax_rate,
        "weight_equity": rb.weight_equity,
        "weight_debt": rb.weight_debt,
        "overridden": override is not None,
    }


def _breakdown_block(b: model.ValueBreakdown, with_rows: bool) -> dict:
    out = {
        "explicit_pv": b.explicit_pv,
        "terminal_pv": b.terminal_pv,
        "total_pv": b.total_pv,
        "terminal_share": b.terminal_share,
    }
    if with_rows:
        out["years"] = [
            {"year": r.year, "growth": r.growth, "cash_flow": r.cash_flow, "pv": r.pv} for r in b.rows
        ]
    return out


def build_report(
    args: argparse.Namespace,
    fetcher: Callable,
    rf_fetch: Callable,
    today: date,
    env: Mapping[str, str],
) -> dict:
    mdl: model.Model = args.model
    years = args.years
    erp = args.erp / 100.0
    g_t = None if args.command == "grid" else args.terminal_growth / 100.0
    override = _pct(args.discount_rate)
    tax_override = _pct(args.tax_rate)
    kd_override = _pct(args.kd)

    # Fail fast on a missing secret, before any network access.
    # An equity discount-rate override does not use rf, so it needs no FRED call or key.
    rf_unused = args.rf is None and mdl == "equity" and override is not None
    api_key = None
    if args.rf is None and not rf_unused:
        api_key = require_fred_key(env)

    c = load_company(args.ticker, fetcher=fetcher, today=today, allow_stale=args.allow_stale, force=args.force,
                     require_positive_fcf=args.fcf is None)

    if args.rf is not None:
        rf = RiskFree(args.rf / 100.0, today, "--rf (user supplied)")
        rf_asof = None
    elif rf_unused:
        rf = RiskFree(None, today, RF_NOT_USED)
        rf_asof = None
    else:
        rf = risk_free(api_key, fetch=rf_fetch, today=today, allow_stale=args.allow_stale)
        rf_asof = rf.obs_date

    if args.beta is not None:
        beta, beta_src = args.beta, "--beta"
    elif c.beta is not None:
        beta, beta_src = c.beta, "yfinance info.beta"
    else:
        raise MissingData(f"{c.ticker}: beta is missing from yfinance. Pass --beta.")

    shares = args.shares * MILLION if args.shares is not None else c.shares
    base_fcf = args.fcf * MILLION if args.fcf is not None else c.ttm_fcf
    if base_fcf <= 0:
        raise DCFInputError(f"{c.ticker}: DCF needs positive TTM FCF (got {base_fcf:,.0f})")

    warnings: list[str] = list(rf.warnings)
    data_warnings = list(c.warnings)
    if args.beta is not None:
        data_warnings = [w for w in data_warnings if not w.startswith("beta missing")]
    if mdl == "equity":
        data_warnings = [w for w in data_warnings if not w.startswith(FCFF_ONLY_PREFIXES)]
    warnings += data_warnings

    net_debt: float | None = None
    interest_added: float | None = None
    base_cf = base_fcf
    if mdl == "fcff" and c.total_debt is None:
        raise MissingData(f"{c.ticker}: the fcff model needs Total Debt on the balance sheet, and it is missing.")
    rb = discount_rate(
        mdl, rf.rate, beta, erp, c.price, shares, c.total_debt, c.ttm_interest,
        c.ttm_tax_provision, c.ttm_pretax_income,
        override=override, tax_override=tax_override, kd_override=kd_override,
    )
    warnings += rb.warnings
    if mdl == "fcff":
        interest = c.ttm_interest
        if interest is None:
            interest = 0.0
            warnings.append("TTM interest expense missing: using 0 in the FCFF base.")
        base_cf = model.fcff_base(base_fcf, interest, rb.tax_rate)
        interest_added = base_cf - base_fcf
        net_debt = c.total_debt - (c.cash or 0.0)
        if c.cash is None:
            warnings.append("Cash missing: net debt uses cash = 0.")

    r = rb.rate
    fade = args.fade
    inputs = _inputs_block(c, args, shares, base_fcf, rf, beta, beta_src, rb, years, g_t, erp, net_debt,
                           base_cf, interest_added)
    inputs["risk_free"]["as_of"] = rf_asof
    report: dict = {
        "command": args.command,
        "ticker": c.ticker,
        "sector": c.sector,
        "model": mdl,
        "model_label": "equity (levered FCF, cost of equity)" if mdl == "equity"
        else "fcff (FCFF, WACC, minus net debt)",
        "growth_path": "fade" if fade else "constant",
        "inputs": inputs,
        "rate": _rate_block(rb, override),
        "warnings": warnings,
    }
    nd = net_debt or 0.0

    if args.command == "implied":
        res = model.implied_growth(c.price, base_cf, r, g_t, years, shares, mdl, fade, nd)
        result: dict = {
            "label": "implied starting growth" if fade else "implied growth",
            "status": res.status,
            "growth": res.growth,
            "bound": res.bound,
        }
        if res.status == "ok":
            path = model.growth_path(res.growth, g_t, years, fade)
            b = model.discount(base_cf, path, r, g_t)
            result["terminal_share"] = b.terminal_share
            result["value_per_share"] = (b.total_pv - (nd if mdl == "fcff" else 0.0)) / shares
            result["breakdown"] = _breakdown_block(b, with_rows=False)
        else:
            result["message"] = (
                f"No solution: price is {'below' if res.status == 'below_lower' else 'above'} the value at "
                f"the {'lower' if res.status == 'below_lower' else 'upper'} bound ({res.bound:.0%})."
            )
        report["result"] = result
    elif args.command == "value":
        g = args.growth / 100.0
        path = model.growth_path(g, g_t, years, fade)
        b = model.discount(base_cf, path, r, g_t)
        vps = (b.total_pv - (nd if mdl == "fcff" else 0.0)) / shares
        report["result"] = {
            "label": "starting growth" if fade else "growth",
            "growth": g,
            "value_per_share": vps,
            "price": c.price,
            "upside": vps / c.price - 1.0,
            "terminal_share": b.terminal_share,
            "breakdown": _breakdown_block(b, with_rows=True),
        }
    else:
        cells = model.grid(c.price, base_cf, r, years, shares, mdl, fade, nd)
        report["result"] = {
            "label": "implied starting growth" if fade else "implied growth",
            "base_discount_rate": r,
            "cells": [
                {
                    "discount_rate": r + off,
                    "offset": off,
                    "terminal_growth": gt,
                    "status": res.status,
                    "growth": res.growth,
                    "bound": res.bound,
                }
                for (off, gt), res in cells.items()
            ],
        }
    return report


# ------------------------------------------------------------------ output

def _p(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x * 100:.{digits}f}%"


def _m(x: float | None) -> str:
    return "n/a" if x is None else f"{x / MILLION:,.0f}M"


def _d(x: date | None) -> str:
    return "user supplied" if x is None else x.isoformat()


def render_text(rep: dict) -> str:
    i, rate, res = rep["inputs"], rep["rate"], rep["result"]
    lines: list[str] = []
    lines.append(f"{rep['ticker']}  sector: {rep['sector'] or 'unknown'}  command: {rep['command']}")
    lines.append(f"Model: {rep['model_label']}; growth path: {rep['growth_path']}")
    lines.append("")
    lines.append("Inputs")
    lines.append(f"  Price:           {i['price']['value']:,.2f}  as of {_d(i['price']['as_of'])}  ({i['price']['source']})")
    lines.append(f"  Shares:          {i['shares']['value'] / MILLION:,.1f}M  ({i['shares']['source']})")
    f = i["levered_fcf"]
    lines.append(f"  TTM levered FCF: {_m(f['value'])}  quarter end {_d(f['as_of'])}  ({f['source']})")
    if rep["model"] == "fcff":
        lines.append(f"  Interest, after tax, added: {_m(i['interest_added_after_tax'])}")
        lines.append(f"  FCFF base:       {_m(i['base_cash_flow'])}")
        lines.append(f"  Total debt:      {_m(i['total_debt']['value'])}; cash: {_m(i['cash']['value'])}"
                 f" ({i['cash']['source'] or 'none'}); net debt: {_m(i['net_debt'])}")
    lines.append(f"  Balance sheet:   as of {_d(i['balance_sheet_date']) if i['balance_sheet_date'] else 'n/a'}"
                 " (shares and debt)")
    if i["risk_free"]["source"] == RF_NOT_USED:
        lines.append("  Risk-free:       not used (--discount-rate replaces the cost of equity)")
    else:
        lines.append(f"  Risk-free:       {_p(i['risk_free']['value'])}  as of {_d(i['risk_free']['as_of'])}  ({i['risk_free']['source']})")
    lines.append(f"  Beta:            {i['beta']['value']:.3f}  ({i['beta']['source']})")
    lines.append(f"  ERP:             {_p(i['erp'])}")
    lines.append(f"  Years:           {i['years']}")
    if i["terminal_growth"] is not None:
        lines.append(f"  Terminal growth: {_p(i['terminal_growth'])}")
    lines.append("")
    lines.append("Discount rate")
    if rate["cost_of_equity"] is None:
        lines.append("  Cost of equity = not computed (rf not used)")
    else:
        lines.append(f"  Cost of equity = rf + beta x ERP = {_p(rate['cost_of_equity'])}")
    if rep["model"] == "fcff":
        lines.append(f"  Cost of debt (pre-tax) = {_p(rate['cost_of_debt'])}; tax rate = {_p(rate['tax_rate'])}")
        lines.append(f"  Weights: equity {_p(rate['weight_equity'], 1)}, debt {_p(rate['weight_debt'], 1)}")
    label = "WACC" if rep["model"] == "fcff" else "Cost of equity"
    note = " (override)" if rate["overridden"] else ""
    lines.append(f"  Discount rate used = {_p(rate['discount_rate'])}  [{label}]{note}")
    if rep["warnings"]:
        lines.append("")
        lines.append("Warnings")
        lines += [f"  - {w}" for w in rep["warnings"]]
    lines.append("")
    lines.append("Result")
    cmd = rep["command"]
    if cmd == "implied":
        if res["status"] == "ok":
            lines.append(f"  {res['label'].capitalize()}: {_p(res['growth'])}")
            if rep["growth_path"] == "fade":
                lines.append(f"  (fades linearly to {_p(i['terminal_growth'])} in year {i['years']})")
            lines.append(f"  Terminal share of value: {_p(res['terminal_share'], 1)}")
            lines.append(f"  Value per share at this growth: {res['value_per_share']:,.2f} (equals price)")
        else:
            lines.append(f"  {res['message']}")
    elif cmd == "value":
        lines.append(f"  {res['label'].capitalize()}: {_p(res['growth'])}")
        lines.append(f"  Value per share: {res['value_per_share']:,.2f}  vs price {res['price']:,.2f}"
                 f"  -> upside {_p(res['upside'], 1)}")
        lines.append(f"  Terminal share of value: {_p(res['terminal_share'], 1)}")
        lines.append("")
        lines.append("  Year   Growth   Cash flow      PV")
        for y in res["breakdown"]["years"]:
            lines.append(f"  {y['year']:>4}  {_p(y['growth'], 1):>7}  {_m(y['cash_flow']):>10}  {_m(y['pv']):>8}")
    else:
        lines.append(f"  {res['label'].capitalize()}; rows: discount rate, columns: terminal growth")
        tgs = sorted({c["terminal_growth"] for c in res["cells"]})
        lines.append("  " + "Discount rate".ljust(14) + "".join(f"g_T {_p(t, 1)}".rjust(14) for t in tgs))
        by_rate: dict[float, dict[float, dict]] = {}
        for c in res["cells"]:
            by_rate.setdefault(c["discount_rate"], {})[c["terminal_growth"]] = c
        for rr, row in by_rate.items():
            cells = []
            for t in tgs:
                c = row[t]
                if c["status"] == "ok":
                    txt = _p(c["growth"])
                elif c["status"] == "invalid":
                    txt = "r <= g_T"
                else:
                    txt = "< -50%" if c["status"] == "below_lower" else "> 100%"
                cells.append(txt.rjust(14))
            lines.append("  " + _p(rr).ljust(14) + "".join(cells))
    return "\n".join(lines)


def _json_default(o):
    if isinstance(o, date):
        return o.isoformat()
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def render_json(rep: dict) -> str:
    return json.dumps(rep, indent=2, default=_json_default, allow_nan=False)


# ------------------------------------------------------------------ entry

def main(
    argv: Sequence[str] | None = None,
    fetcher: Callable = yf_fetch,
    rf_fetch: Callable = fred_fetch,
    today: date | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if env is None:
        load_dotenv(dotenv_path=Path.cwd() / ".env")
        env = os.environ
    today = today or date.today()
    try:
        if not 1 <= args.years <= model.MAX_YEARS:
            raise ValueError(f"--years must be an integer from 1 to {model.MAX_YEARS}, got {args.years}")
        for name in ("erp", "beta", "rf", "discount_rate", "tax_rate", "kd", "fcf", "shares"):
            v = getattr(args, name)
            if v is not None and not math.isfinite(v):
                raise ValueError(f"--{name.replace('_', '-')} must be a finite number")
        if args.shares is not None and args.shares <= 0:
            raise ValueError("--shares must be positive")
        report = build_report(args, fetcher, rf_fetch, today, env)
    except (DCFInputError, ValueError) as e:
        msg = " ".join(str(e).split())
        print(f"error: {msg}", file=sys.stderr)
        return EXIT_CODE
    print(render_json(report) if args.json else render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
