# Spec: lean reverse-DCF tool

Status: draft, not approved. Date: 2026-10-22.
Source: the revival audit of 2026-10-22 (summary in "Why" below).

## Goal

Answer one question per ticker: **"What free-cash-flow growth does today's price imply, and how
sensitive is that answer to my assumptions?"** Also give a forward value for growth, discount
rate, and terminal growth that the user chooses.

The tool is a thinking aid for one stock at a time. It does not make buy or sell signals.

## Why (from the audit)

- The current engine gives unusable output (median upside −44% on 43 large caps). The causes
  are a 65% terminal-value cap, non-monotonic growth cleaning, a CAPE adjustment from 2023 data,
  and FCF = latest quarter × 4.
- A DCF "upside" score is a value signal. quant-portfolio-manager already tested value on
  point-in-time SEC data, and it failed. So ranking stocks by DCF upside is out of scope.
- The reverse DCF does not need a growth forecast from the tool. The user judges the implied
  growth. That removes the weakest part of the old design.

## Non-goals

No Monte Carlo. No automatic growth cleaning or sector priors. No relative-valuation blend.
No portfolio optimization, regime detection, or backtest. No EV/Sales fallback. No multi-ticker
ranking. No XBRL parser.

## Usage (target CLI)

```bash
uv run dcf implied KO
uv run dcf implied KO --years 10 --terminal-growth 2.5 --erp 5.0 --json
uv run dcf value KO --growth 6 --discount-rate 8.5
uv run dcf grid KO
```

- `implied`: solve for the growth rate that makes the model value equal to the market price.
- `value`: value per share for user inputs, with upside versus price.
- `grid`: implied growth for discount rate (base ±1 and ±2 pp) × terminal growth (1.5, 2.5, 3.5%).
- Every command prints its inputs, data sources, and data as-of dates. `--json` gives the same
  content as JSON.

## Model

Equity DCF on levered free cash flow (FCFE-style), discounted at the cost of equity:

```
FCF_t   = FCF_0 × (1 + g)^t                       for t = 1..N
TV_N    = FCF_N × (1 + g_T) / (r − g_T)
Value   = Σ FCF_t / (1 + r)^t  +  TV_N / (1 + r)^N
Per share = Value / shares
```

- No terminal-value cap. The output shows the terminal share of value for information.
- Growth is constant for N years (default N = 10). A fade option is open question 3.
- Implied growth: solve `Value(g)/shares = price` with `scipy.optimize.brentq` on
  g ∈ [−50%, +100%]. If no root exists in the bracket, report which bound fails. Do not
  extrapolate.
- `Value(g)` must increase strictly with g when FCF_0 > 0. This is what makes the root unique.

## Inputs and defaults

| Input | Source / default | Override |
|---|---|---|
| FCF_0 | TTM: sum of the last 4 quarters of (Operating Cash Flow − \|Capital Expenditure\|). Fallback: sum of the "Free Cash Flow" row. | `--fcf` (millions) |
| Shares | Latest quarterly "Ordinary Shares Number"; fallback `info.sharesOutstanding` | `--shares` |
| Price | Last daily close, with its date | — |
| r (discount rate) | rf + β × ERP | `--discount-rate` |
| rf | FRED `DGS10`, latest observation, with its date | `--rf` |
| β | yfinance `info.beta`, shown, not clipped | `--beta` |
| ERP | 5.0% | `--erp` |
| g_T | 2.5% | `--terminal-growth` |
| N | 10 years | `--years` |

## Refusals and errors (exit code 2, one clear message)

- TTM FCF ≤ 0: "DCF needs positive TTM FCF". No fallback method.
- Sector is "Financial Services": refuse, because FCF is not meaningful for banks and
  insurers. `--force` runs it with a warning.
- r ≤ g_T, or fewer than 4 quarters of cash-flow data.
- `FRED_API_KEY` is not set and `--rf` is not given: name the missing variable and `.env`.

## Runtime contracts (assert at the data boundary)

- All numeric inputs are finite. Shares > 0. Price > 0.
- Quarter end dates are unique and in ascending order after the sort.
- Freshness: the latest quarter end ≤ 200 days old. The price date ≤ 7 calendar days old.
  The FRED observation ≤ 10 days old. If a check fails, stop with the actual date, unless
  `--allow-stale` is given. In that case print a warning with the date.

## Keep / drop (from the current repo)

| Keep (rewrite small) | Drop |
|---|---|
| DCF loop from `calculate_dcf`, without the cap | Terminal-value cap, exit-multiple method |
| `brentq` reverse solve from `calculate_implied_growth` | Growth cleaning, sector priors and caps |
| FRED 10Y fetch (simplified, with date check) | Shiller CAPE, Damodaran loader |
| uv + pyproject + ruff | Monte Carlo, scenarios, stress test |
| | Relative valuation, PEG, 60/40 blend, conflict logic |
| | Black-Litterman, optimizer, regime detection |
| | Backtest, XBRL parser, download scripts |
| | Questionary menu, Pydantic layer, logging framework |
| | 22 analysis docs in `docs/` (keep `HANDOFF.md`) |

The legacy code stays reachable through a git tag (see the plan).

## Acceptance criteria

1. `uv run pytest -q` passes offline. A `conftest.py` guard fails any non-`integration` test
   that opens a network socket.
2. Property tests (Hypothesis): value increases with g and decreases with r. Round trip:
   `implied(value(g)) == g` within 1e-6 for every g in the bracket.
3. A closed-form check: one hand-computed case matches to 1e-9.
4. Golden test: `implied --json` on a saved KO fixture matches a saved JSON output.
5. `ruff check` is clean. Every command in the README runs in a regression test.
6. A live run of `dcf implied` on AAPL, KO and XOM gives an answer with as-of dates. A live
   run on JPM refuses with the financials message.

## Open questions (default in bold)

1. **Rebuild in this repo** (tag the legacy code, then delete it) or start a new repo?
2. **Equity DCF on levered FCF at cost of equity** or FCFF + WACC − net debt? FCFF needs
   interest expense, and yfinance does not give it for every company (AAPL has no row).
3. **Constant growth for N years** or a linear fade from g to g_T?
4. ERP default: **5.0%**, or another value?
