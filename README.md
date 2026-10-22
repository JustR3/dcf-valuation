# dcf-valuation

A lean reverse-DCF tool for one stock at a time.

It answers one question: **what free-cash-flow growth does today's price imply, and how
sensitive is that answer to my assumptions?** It can also value a stock for a growth rate, a
discount rate, and a terminal growth rate that you choose.

It is a thinking aid. It does not give buy or sell signals and it does not rank stocks.

## Install

Python 3.12 or newer and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --extra dev
uv run dcf --help
```

## Set up `.env`

The risk-free rate comes from FRED (series `DGS10`). Get a free key at
<https://fred.stlouisfed.org/docs/api/api_key.html>, then:

```bash
cp .env.example .env
```

Edit `.env` and set `FRED_API_KEY=<your key>`. Run `dcf` from the folder that holds `.env`. You do
not need a key when you pass `--rf` yourself. Never commit `.env`.

## Commands

```bash
uv run dcf implied KO
uv run dcf implied KO --years 10 --terminal-growth 2.5 --erp 5.0 --json
uv run dcf implied KO --model fcff --fade
uv run dcf implied AAPL --model fcff
uv run dcf implied KO --rf 4.2 --beta 0.6
uv run dcf value KO --growth 6 --discount-rate 8.5
uv run dcf value KO --growth 6 --fade --model fcff
uv run dcf grid KO
uv run dcf grid KO --model fcff --fade --json
```

- `implied`: solve for the growth rate that makes the model value equal the market price.
  With `--fade` the answer is the *implied starting growth*.
- `value`: value per share for the `--growth` you give, with upside versus the price.
- `grid`: implied growth for discount rate (base -2, -1, 0, +1, +2 points) by terminal growth
  (1.5%, 2.5%, 3.5%). A cell shows `< -50%` or `> 100%` when no root exists inside the search
  range of -50% to +100%.

Every command prints its inputs with sources and as-of dates (price date, latest quarter end,
balance sheet date, FRED date), the model name, the rate breakdown, warnings, and the result. `--json` prints the same
content as JSON: dates are ISO strings and numbers are decimals (0.05 = 5%).

Exit code `0` means success. Exit code `2` means a refusal or an input error, with one line on
stderr:

```bash
uv run dcf implied JPM   # exit 2
```

## Flags

Percent flags take percent: `--erp 5` means 5%.

| Flag | Meaning | Default |
|---|---|---|
| `--model equity\|fcff` | Cash-flow model | `equity` |
| `--fade` | Growth falls linearly from the start rate to terminal growth | constant growth |
| `--years N` | Explicit forecast years (1 to 30) | 10 |
| `--terminal-growth` | Terminal growth, percent (`implied`, `value`) | 2.5 |
| `--erp` | Equity risk premium, percent | 5.0 |
| `--beta` | Beta. Required when yfinance has none | yfinance `info.beta` |
| `--rf` | Risk-free rate, percent. Skips FRED | FRED `DGS10` |
| `--discount-rate` | Replace the computed discount rate, percent | Ke or WACC |
| `--tax-rate` | `fcff`: tax rate, percent | TTM tax / TTM pretax income |
| `--kd` | `fcff`: pre-tax cost of debt, percent | TTM interest / total debt |
| `--fcf` | Base TTM free cash flow, in millions | TTM from the filings |
| `--shares` | Shares outstanding, in millions | latest quarterly count |
| `--growth` | `value` only: growth rate, percent | required |
| `--json` | Print JSON | text |
| `--force` | Run Financial Services companies anyway, with a warning | off |
| `--allow-stale` | Continue with stale data, with a warning | off |

## Model

One discounting core serves both models. `CF_0` is the base cash flow, `g_t` is the growth path,
`r` is the discount rate and `g_T` is the terminal growth.

```
CF_t = CF_{t-1} * (1 + g_t)          t = 1..N
TV_N = CF_N * (1 + g_T) / (r - g_T)
PV   = sum CF_t / (1 + r)^t  +  TV_N / (1 + r)^N
```

- Constant path: `g_t = g`. Fade path: `g_t = g + (g_T - g) * (t - 1) / (N - 1)`.
- There is no terminal-value cap. The output shows the terminal share of value.
- `equity` (default): base = TTM levered FCF. `r` = cost of equity = rf + beta x ERP. Equity
  value = PV.
- `fcff`: base = TTM levered FCF + TTM interest x (1 - t). `r` = WACC =
  E/(D+E) x Ke + D/(D+E) x Kd x (1 - t), with E = price x shares and D = latest total debt.
  Equity value = PV - net debt (total debt - cash).
- TTM levered FCF = sum of the last 4 quarters of (Operating Cash Flow - |Capital Expenditure|).
  The four quarters must be consecutive.
- Implied growth is found with `scipy.optimize.brentq` on g in [-50%, +100%]. Value per share
  increases with g, so the root is unique.

## Refusals (exit code 2)

- TTM FCF is zero or negative: "DCF needs positive TTM FCF". There is no fallback method.
- Sector is Financial Services (banks, insurers): FCF is not meaningful. `--force` overrides.
- The discount rate is not above terminal growth, or fewer than 4 quarters of cash-flow data.
- `--model fcff` and the balance sheet has no Total Debt.
- Beta is missing from yfinance and `--beta` is not given.
- `FRED_API_KEY` is not set and `--rf` is not given.
- Price currency differs from the financial statement currency (yfinance `currency` and
  `financialCurrency`). There is no override flag.
- The price date is more than 1 day after today.
- A data source fails (yfinance error, FRED HTTP or network error, malformed FRED row).
- A growth rate (`--growth`, `--terminal-growth`) is -100% or lower.
- Stale data: latest quarter end older than 200 days, price older than 7 days, FRED observation
  older than 10 days. `--allow-stale` continues and prints a warning with the date.

## Limits

- **equity vs fcff.** The two models give different answers for the same stock. `equity` is
  simple and uses cost of equity; it fits companies with stable, small debt. `fcff` adds back
  after-tax interest and subtracts net debt, so it fits companies with large debt. It uses book
  debt in WACC, which adds model error. The output always names the model.
- **Fallbacks, always shown as warnings.** Tax rate 21% when pretax income is zero or negative
  or a row is missing. Interest 0 in the FCFF base when the row is missing (for example AAPL).
  Kd = rf + 1.5% when interest is missing or debt is 0. Cash = 0 when no cash row exists.
  Shares fall back to `info.sharesOutstanding`.
- **Split check.** If the balance-sheet share count and `info.sharesOutstanding` differ by more
  than a factor of 1.5, a warning names both counts: a split may have happened after the quarter
  end.
- **Older columns.** When a TTM sum, the share count, debt or cash uses a quarter older than the
  newest column of its table, a warning names the row and the date used. The balance sheet date
  of the debt and share values is printed with the inputs.
- **Price.** The price is the latest close that yfinance returns. It may be an intraday value
  while the market is open. Its date is printed.
- **`--discount-rate` with `equity`.** The risk-free rate is not used, so the tool does not
  call FRED, does not need `FRED_API_KEY`, and shows the risk-free rate as "not used". The
  `fcff` model still needs it.
- **Leases in debt.** yfinance "Total Debt" may include lease liabilities, so FCFF net debt can
  double-count leases. The `equity` model is not affected.
- **Beta is not clipped.** A very low beta (KO is about 0.3) gives a low discount rate and a high
  terminal share of value. Judge the result with `grid`.
- **Financials.** Card networks and brokers can pass the sector check but still have unreliable
  FCF. The output shows the sector.
- **Negative TTM FCF.** The tool refuses it, unless you pass your own positive `--fcf`. Then the
  output shows a warning with the reported TTM FCF.
- Data comes from yfinance (price, statements) and FRED (rate). Names of yfinance rows can
  change; the offline tests use recorded fixtures.

## Tests

```bash
uv run pytest -q
uv run ruff check .
```

The test suite runs offline. A guard in `tests/conftest.py` fails any test that opens a network
socket unless it is marked `integration`. `tests/test_readme_commands.py` runs every
`uv run dcf` example in this file.
