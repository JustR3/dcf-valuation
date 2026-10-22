"""CLI tests: smoke test of the real entry point, refusals, and golden JSON outputs. Offline."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from dcf.cli import main

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden"
TODAY = date(2026, 10, 22)
ENV = {"FRED_API_KEY": "test-key"}


def fetcher(ticker: str) -> dict:
    return json.loads((FIXTURES / f"{ticker.upper()}.json").read_text())


def fred(api_key, series="DGS10"):
    return json.loads((FIXTURES / "fred_dgs10.json").read_text())


def run(argv, env=ENV, rf_fetch=fred, today=TODAY):
    return main(argv, fetcher=fetcher, rf_fetch=rf_fetch, today=today, env=env)


def assert_close(actual, expected, path="$"):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys(), path
        for k in expected:
            assert_close(actual[k], expected[k], f"{path}.{k}")
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), path
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            assert_close(a, e, f"{path}[{i}]")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=1e-9, abs=1e-12), path
    else:
        assert actual == expected, path


def test_smoke_text_output(capsys):
    assert run(["implied", "KO"]) == 0
    out = capsys.readouterr().out
    assert "Implied growth:" in out
    assert "Terminal share of value" in out
    assert "2026-10-22" in out  # price date
    assert "2026-06-30" in out  # quarter end
    assert "2026-10-20" in out  # FRED observation date


def test_fade_label(capsys):
    assert run(["implied", "KO", "--fade"]) == 0
    assert "Implied starting growth:" in capsys.readouterr().out


def test_value_and_grid_run(capsys):
    assert run(["value", "KO", "--growth", "6", "--discount-rate", "8.5"]) == 0
    assert "upside" in capsys.readouterr().out
    assert run(["grid", "KO", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert len(rep["result"]["cells"]) == 15


def test_aapl_fcff_warns_about_interest(capsys):
    assert run(["implied", "AAPL", "--model", "fcff", "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert any("interest" in w.lower() for w in rep["warnings"])


def test_rf_flag_skips_fred_and_key(capsys):
    def boom(*a, **k):
        raise AssertionError("FRED must not be called")

    assert run(["implied", "KO", "--rf", "4.2"], env={}, rf_fetch=boom) == 0
    assert "--rf" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "env", "today", "fragment"),
    [
        (["implied", "JPM"], ENV, TODAY, "Financial Services"),
        (["implied", "KO"], {}, TODAY, "FRED_API_KEY"),
        (["implied", "KO"], ENV, date(2026, 12, 31), "days old"),  # FRED + price stale
        (["implied", "KO", "--discount-rate", "2", "--terminal-growth", "3"], ENV, TODAY, "exceed"),
        (["implied", "KO", "--years", "0"], ENV, TODAY, "years"),
    ],
)
def test_refusals_exit_2(argv, env, today, fragment, capsys):
    assert run(argv, env=env, today=today) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    lines = cap.err.strip().splitlines()
    assert len(lines) == 1
    assert fragment in lines[0]


def test_stale_fred_exit_2(capsys):
    old = {"observations": [{"date": "2026-09-01", "value": "4.1"}]}
    assert run(["implied", "KO"], rf_fetch=lambda k, s="DGS10": old) == 2
    err = capsys.readouterr().err
    assert "FRED" in err and "2026-09-01" in err


def test_stale_allowed_prints_warning(capsys):
    assert run(["implied", "KO", "--allow-stale", "--json"], today=date(2026, 12, 31)) == 0
    rep = json.loads(capsys.readouterr().out)
    assert any("old" in w for w in rep["warnings"])


def test_fcff_without_debt_refused(capsys):
    raw = fetcher("KO")
    del raw["balance"]["Total Debt"]
    assert main(["implied", "KO", "--model", "fcff"], fetcher=lambda t: raw, rf_fetch=fred,
                today=TODAY, env=ENV) == 2
    assert "Total Debt" in capsys.readouterr().err


def test_missing_beta_refused(capsys):
    raw = fetcher("KO")
    raw["info"]["beta"] = None
    assert main(["implied", "KO"], fetcher=lambda t: raw, rf_fetch=fred, today=TODAY, env=ENV) == 2
    assert "beta" in capsys.readouterr().err
    assert main(["implied", "KO", "--beta", "0.6"], fetcher=lambda t: raw, rf_fetch=fred,
                today=TODAY, env=ENV) == 0


@pytest.mark.parametrize(
    ("name", "argv"),
    [
        ("ko_implied_equity", ["implied", "KO", "--json"]),
        ("ko_implied_fcff_fade", ["implied", "KO", "--model", "fcff", "--fade", "--json"]),
    ],
)
def test_golden(name, argv, capsys):
    assert run(argv) == 0
    actual = json.loads(capsys.readouterr().out)
    expected = json.loads((GOLDEN / f"{name}.json").read_text())
    assert_close(actual, expected)


def test_fcf_override_rescues_negative_ttm_fcf(capsys):
    # JPM has negative TTM FCF; with --force and an explicit positive --fcf the run proceeds.
    assert run(["implied", "JPM", "--force", "--fcf", "50000", "--json"]) == 0
    assert '"--fcf"' in capsys.readouterr().out


def test_fcf_override_must_be_positive():
    assert run(["implied", "KO", "--fcf", "-5"]) == 2
