"""Record raw yfinance data for a ticker to a JSON fixture.

Usage: .venv/bin/python tools/capture_fixture.py TICKER [--out tests/fixtures]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dcf.data import yf_fetch  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ticker")
    p.add_argument("--out", default="tests/fixtures")
    args = p.parse_args(argv)
    raw = yf_fetch(args.ticker)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{args.ticker.upper()}.json"
    path.write_text(json.dumps(raw, indent=1, sort_keys=True))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
