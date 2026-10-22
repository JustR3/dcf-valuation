# Decisions

Mid-run choices made during the build, newest last. User decisions live in the spec.

- 2026-10-22 (task 3): TTM sums the 4 latest quarters that have data only when they are
  consecutive (each step 60–120 days). Otherwise `MissingData` for FCF, or `None` plus a
  warning for an FCFF-only row. Reason: skipping a missing quarter mixed in a quarter from the
  year before, with no warning. The task-3 Hypothesis oracle (uncommitted, written this session)
  encoded the old skip rule; it was tightened to the spec's "last 4 quarters" meaning.
- 2026-10-22 (task 3): `load_company` reports a missing total-debt row as `None` plus a warning.
  The `fcff`-mode refusal is raised later, where the model is known (rates/CLI).
- 2026-10-22 (task 4): `StaleRate` and `MissingSecret` live in `dcf/rates.py` and subclass
  `DCFInputError`, so every refusal maps to exit code 2.
- 2026-10-22 (task 5): `--fcf` and `--shares` are in millions (spec says millions for `--fcf`; `--shares` follows it).
  `grid` has no `--terminal-growth` flag, because it sweeps 1.5, 2.5 and 3.5%. The CLI checks `FRED_API_KEY`
  before any network call. In `equity` mode the fcff-only data warnings are hidden.
- 2026-10-22 (task 5 review): `load_company(require_positive_fcf=...)`. The CLI sets it to False
  when `--fcf` is given, so the spec's `--fcf` override also works for a negative-TTM-FCF company
  (with a warning). The CLI still refuses a non-positive base FCF.
- 2026-10-22 (review): Applied 11 Auto-fix findings (currency mismatch refusal, split warning,
  roll-back warnings + balance_sheet_date, g/g_T > -100%, FCF-row fallback on gaps, network
  errors -> exit 2, sector-None warning, Kd > 15% warning, future price refusal, equity
  --discount-rate without FRED, wider round-trip test). The goldens gained `balance_sheet_date`
  and the new price label; their numbers did not change.
- 2026-10-22 (review, Ask-user, not changed): unit-sanity warnings for percent/millions flags;
  lease liabilities inside yfinance "Total Debt" for FCFF net debt (documented as a limit only).
- 2026-10-22 (user): both Ask-user items resolved as "keep". FCFF net debt keeps yfinance
  "Total Debt" (lease double-count stays a documented limit). No unit-sanity warnings for now.
