"""Every `uv run dcf ...` example in README.md must still parse and run (offline, KO/AAPL/JPM fixtures)."""

from __future__ import annotations

import json
import re
import shlex
from datetime import date
from pathlib import Path

import pytest

from dcf.cli import build_parser, main

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text()
FIXTURES = ROOT / "tests" / "fixtures"
TODAY = date(2026, 10, 22)
ALLOWED_TICKERS = {"KO", "AAPL", "JPM"}


def readme_commands() -> list[tuple[str, int]]:
    """(command line, expected exit code) for each `uv run dcf` line in a fenced code block."""
    cmds: list[tuple[str, int]] = []
    for block in re.findall(r"```[a-z]*\n(.*?)```", README, flags=re.S):
        for line in block.splitlines():
            if line.startswith("uv run dcf"):
                m = re.search(r"#\s*exit\s+(\d+)\s*$", line)
                cmds.append((line, int(m.group(1)) if m else 0))
    return cmds


def fetcher(ticker: str) -> dict:
    return json.loads((FIXTURES / f"{ticker.upper()}.json").read_text())


def fred(api_key, series="DGS10"):
    return json.loads((FIXTURES / "fred_dgs10.json").read_text())


def test_readme_has_commands():
    assert len(readme_commands()) >= 8


@pytest.mark.parametrize(("line", "expected"), readme_commands())
def test_readme_command_runs(line, expected, capsys):
    argv = shlex.split(line, comments=True)[3:]  # drop: uv run dcf
    if "--help" in argv:
        with pytest.raises(SystemExit) as exc:
            main(argv)
        assert exc.value.code == expected
        return
    assert argv[1] in ALLOWED_TICKERS
    code = main(argv, fetcher=fetcher, rf_fetch=fred, today=TODAY, env={"FRED_API_KEY": "test-key"})
    assert code == expected
    cap = capsys.readouterr()
    if "--json" in argv and expected == 0:
        json.loads(cap.out)


def test_every_flag_and_command_is_documented():
    parser = build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    for name, p in sub.choices.items():
        assert f"`{name}`" in README
        for action in p._actions:
            for opt in action.option_strings:
                if opt.startswith("--") and opt != "--help":
                    assert f"`{opt}" in README, f"{opt} (dcf {name}) missing from README"
