# Handoff Log

One line per completed plan task, newest last.

- 2026-09-08: handoff log started (no retroactive backfill of prior work; see git log for history before this point).
- 2026-10-22: task 1 — tagged main as legacy-v1 (pushed), deleted legacy src/, tests/, scripts/, main.py, 22 analysis docs, pre-commit config.
- 2026-10-22: task 2 — dcf/model.py core math (growth paths, discount, fcff/wacc, implied growth, grid); 54 tests incl. Hypothesis.
- 2026-10-22: task 3 — dcf/data.py (CompanyInputs, TTM with contiguity check, freshness, refusals), errors, capture tool, KO/AAPL/JPM fixtures; 28 tests.
- 2026-10-22: task 4 — dcf/rates.py (FRED DGS10 with freshness, cost of equity, WACC with spec fallbacks), .env.example; 24 tests. Key moved to ignored .env.
- 2026-10-22: task 5 — dcf/cli.py (implied/value/grid, --model, --fade, --json), golden tests for KO equity and fcff+fade; --fcf override fix in data.py.
- 2026-10-22: task 6 — pyproject 2.0.0 with 6 runtime deps and dcf entry point, uv.lock, offline socket guard in tests/conftest.py.
- 2026-10-22: task 7 — README rewritten as the owner doc; tests/test_readme_commands.py runs every documented command.
- 2026-10-22: task 8 — reviewer findings triaged and applied (185 tests); live check: AAPL/KO/XOM ok in both models with current dates, JPM refused (financials), TSM refused (currency).
- 2026-10-24: CI — added .github/workflows/test.yml (offline pytest + ruff check, permissions: contents: read); .gitignore now tracks workflows.
