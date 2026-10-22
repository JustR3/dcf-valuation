# Plan: lean reverse-DCF tool

Spec: [2026-10-22-lean-reverse-dcf-design.md](../specs/2026-10-22-lean-reverse-dcf-design.md).
Status: not started. Uses the user's answers in the spec's "Decisions" section (both models,
both growth paths, ERP 5.0%, rebuild here with legacy deletion approved).

Branch: `feat/lean-reverse-dcf` from `main`. Size estimate: about 700 lines of source and
600 lines of tests (about 1 day more than the single-model version). Routing: Opus writes the spec, plan, and review. The `implementer` agent
(Sonnet) does tasks 2–6. Each checkpoint runs the full suite, commits `task N: <summary>`, and
appends one line to `docs/HANDOFF.md`.

## Target layout

```
dcf/__init__.py
dcf/model.py      # pure math: growth paths, discounting, equity/fcff, implied_growth, grid
dcf/data.py       # yfinance -> CompanyInputs (TTM FCF, interest, tax, debt, cash, shares, price, beta, dates)
dcf/rates.py      # FRED DGS10 -> rf with date; cost of equity; WACC
dcf/cli.py        # argparse: implied | value | grid, --json
tools/capture_fixture.py
tests/conftest.py # offline guard + `integration` marker
tests/fixtures/   # recorded yfinance frames for KO, AAPL, JPM; one FRED response
tests/test_model.py, test_data.py, test_rates.py, test_cli.py, test_readme_commands.py
```

## Tasks

### Task 1 — Archive the legacy code (deletion approved by the user on 2026-10-22)
- Tag `main` as `legacy-v1` and push the tag.
- Delete `src/`, `scripts/`, `tests/`, `main.py`, the 22 analysis docs in `docs/`, and
  `.pre-commit-config.yaml` (it has a Poetry hook in a uv project). Keep `docs/HANDOFF.md`,
  `docs/superpowers/`, `LICENSE`, and `config/` (ignored, holds the local key).
- Approach: verify (no code). Check: `git ls-files` shows only the kept files, and
  `git show legacy-v1:src/dcf_engine.py` works.

### Task 2 — Core math `dcf/model.py` (own checkpoint: core calculation)
- Pure functions, no I/O:
  - `growth_path(g, g_t, years, fade: bool) -> list[float]`.
  - `discount(base_cf, path, r, g_t) -> ValueBreakdown` (explicit PV, terminal PV, terminal
    share, per-year rows).
  - `fcff_base(levered_fcf, interest, tax_rate)`, `wacc(e, d, ke, kd, tax_rate)` (pure; the
    data-dependent fallbacks live in task 3/4).
  - `per_share(inputs, g, model, fade)`: equity mode = PV / shares; fcff mode =
    (PV − net debt) / shares.
  - `implied_growth(...) -> ImpliedResult` (root or the failing bound), `grid(...)`.
- Contracts: finite inputs, base cash flow > 0, r > g_t, 1 ≤ years ≤ 30, 0 ≤ tax rate < 1.
- Approach: batch TDD. Hypothesis properties for all 4 combinations (equity/fcff ×
  constant/fade): monotonic in g and r; round trip `implied(value(g)) == g` within 1e-6;
  terminal share in (0, 1). Hand-computed cases to 1e-9 for each growth path. With g = g_T, the
  constant and fade paths give the same value. Fade path: first element = g, last = g_T.
- Acceptance: `tests/test_model.py` passes. No network import in `model.py`.

### Task 3 — Data layer `dcf/data.py` + `tools/capture_fixture.py`
- `load_company(ticker, fetcher=yf_fetch) -> CompanyInputs`. Inject the fetcher so tests use
  fixtures.
- TTM FCF from the last 4 quarters (OCF − |capex|, fallback "Free Cash Flow" row). Shares from
  "Ordinary Shares Number", fallback `sharesOutstanding`. Keep each as-of date.
- For `fcff`: TTM interest expense, TTM tax provision, TTM pretax income, latest total debt,
  latest cash (two row names, in the spec order). Each missing optional row is `None` plus a
  warning string; the fallbacks (t = 21%, interest = 0, Kd = rf + 1.5%) are applied in one
  place and listed in the output. Missing total debt in `fcff` mode raises `MissingData`.
- Contracts and freshness checks from the spec. Raise typed errors: `NegativeFCF`,
  `FinancialsSector`, `StaleData`, `MissingData`.
- `tools/capture_fixture.py TICKER` records the raw frames to `tests/fixtures/` (test-after).
- Approach: batch TDD on the parsing with the KO, AAPL (no interest row), and JPM fixtures.
  Hypothesis for malformed frames (NaN, missing rows, fewer than 4 quarters, duplicate dates).
- Acceptance: `tests/test_data.py` passes offline.

### Task 4 — Rates `dcf/rates.py`
- `risk_free(api_key, fetch=...) -> (rate, obs_date)` from FRED `DGS10`; freshness ≤ 10 days.
- `cost_of_equity(rf, beta, erp)` with ERP default 5.0%.
- `discount_rate(inputs, model, overrides)`: Ke for `equity`; WACC for `fcff`, with the Kd and
  tax fallbacks from the spec. `--discount-rate` overrides both.
- Fail fast when `FRED_API_KEY` is missing and no `--rf`: name the variable and `.env`.
- Move the key from `config/secrets.env` to `.env`; add `.env.example`.
- Approach: batch TDD with a recorded FRED response.
- Acceptance: `tests/test_rates.py` passes offline.

### Task 5 — CLI `dcf/cli.py`
- Subcommands `implied`, `value`, `grid`; flags from the spec, including `--model equity|fcff`,
  `--fade`, `--tax-rate`, `--kd`; `--json`, `--force`, `--allow-stale`. Exit 2 on refusals,
  with one message line.
- With `--fade`, label the result "implied starting growth".
- Output always shows inputs, sources, and as-of dates. Use plain text tables (`rich` only if
  it stays a single small dependency).
- Approach: test-after + golden tests. One smoke test runs the real entry point on the KO
  fixture. Two golden JSON files (`implied --json` and `implied --model fcff --fade --json`) are
  checked by hand once, then saved.
- Acceptance: `tests/test_cli.py` passes; `uv run dcf --help` works.

### Task 6 — Packaging and tooling (small; may share a checkpoint with task 7)
- `pyproject.toml`: entry point `dcf = "dcf.cli:main"`; dependencies only `yfinance`,
  `pandas`, `numpy`, `scipy`, `requests`, `python-dotenv`; dev: `pytest`, `hypothesis`, `ruff`.
  Run `uv lock`.
- `tests/conftest.py`: socket guard and `integration` marker (copy the pattern from
  quant-portfolio-manager).
- Approach: verify. Check: `uv sync`, `ruff check`, full suite.

### Task 7 — README and doc regression test
- Rewrite `README.md` as the owner file for usage, flags, env vars, and model limits.
- `tests/test_readme_commands.py`: extract every `uv run dcf ...` line from the README and run
  it against fixtures.
- Approach: test-after.

### Task 8 — Final verification and review
- Full suite + `ruff check`. Live run on AAPL, KO, XOM in both models (answers with dates;
  AAPL `fcff` shows the interest fallback warning) and JPM (refusal).
- Run the `reviewer` agent with the spec and the diff (required: the diff touches core
  calculation and data ingestion). Triage findings as Auto-fix / No-op / Ask-user.
- Push the branch and open a draft PR. You merge.

## Callers to update

A grep at build time must confirm nothing outside this repo imports `src.dcf_engine`.
quant-portfolio-manager has no import, only a stale hint at `main.py:610` (`dcf_cli.py`).
That fix is a separate one-line PR in that repo and is not part of this plan.

## Risks

- yfinance field names change. Mitigation: fixtures plus one `integration` test per field.
- Bank-like companies outside "Financial Services" (for example, card networks or brokers)
  can still pass. The output shows the sector so the user can judge.
- Implied growth for a 10-year constant rate can look high for long-duration names. That is
  the expected answer of the model, not a defect. The grid shows the sensitivity.
- `equity` and `fcff` give different answers for the same stock. Book debt in WACC and the
  fallbacks add model error. The output always names the model, and the README explains when
  each one fits.
