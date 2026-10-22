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
