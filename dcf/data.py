"""Data layer: fetch raw company data and turn it into validated CompanyInputs."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from dcf.errors import FinancialsSector, MissingData, NegativeFCF, StaleData

# Raw data shape returned by a fetcher (plain, JSON-serialisable):
# {
#   "ticker": str,
#   "info": {"sector": str|None, "beta": float|None, "sharesOutstanding": float|None},
#   "cashflow": {row: {"YYYY-MM-DD": value}},   # quarterly
#   "income":   {row: {"YYYY-MM-DD": value}},   # quarterly
#   "balance":  {row: {"YYYY-MM-DD": value}},   # quarterly
#   "prices":   {"YYYY-MM-DD": close},          # daily closes
# }
RawData = dict

MAX_QUARTER_AGE_DAYS = 200
MAX_PRICE_AGE_DAYS = 7

CASH_ROWS = (
    "Cash Cash Equivalents And Short Term Investments",
    "Cash And Cash Equivalents",
)


def _clean(value):
    """Return a finite float, or None for missing / NaN / inf / non-numeric."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def yf_fetch(ticker: str) -> RawData:
    """Fetch raw data from yfinance and serialise frames as {row: {date: value}}."""
    import yfinance as yf

    t = yf.Ticker(ticker)

    def frame(df) -> dict:
        out: dict = {}
        if df is None or getattr(df, "empty", True):
            return out
        for row in df.index:
            series = df.loc[row]
            out[str(row)] = {
                str(col.date() if hasattr(col, "date") else col): _json_num(v)
                for col, v in series.items()
            }
        return out

    info = t.info or {}
    hist = t.history(period="1mo", auto_adjust=False)
    prices = {}
    if hist is not None and not hist.empty:
        prices = {str(i.date()): _json_num(v) for i, v in hist["Close"].items()}
    return {
        "ticker": ticker.upper(),
        "info": {k: info.get(k) for k in ("sector", "beta", "sharesOutstanding")},
        "cashflow": frame(t.quarterly_cashflow),
        "income": frame(t.quarterly_income_stmt),
        "balance": frame(t.quarterly_balance_sheet),
        "prices": prices,
    }


def _json_num(v):
    f = _clean(v)
    return f  # NaN / inf become None (JSON null)


@dataclass(frozen=True)
class CompanyInputs:
    ticker: str
    sector: str | None
    price: float
    price_date: date
    shares: float
    shares_source: str
    ttm_fcf: float
    fcf_source: str
    latest_quarter_end: date
    beta: float | None
    # fcff-only fields; None means the row was missing (see warnings)
    ttm_interest: float | None = None
    ttm_tax_provision: float | None = None
    ttm_pretax_income: float | None = None
    total_debt: float | None = None
    cash: float | None = None
    cash_source: str | None = None
    warnings: tuple[str, ...] = field(default=())


def _parse_date(s) -> date:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError as e:
        raise MissingData(f"Unreadable date {s!r} in fetched data") from e


def _series(frame: dict, row: str) -> dict[date, float | None] | None:
    """Row of a serialised frame as {date: finite float or None}. None if row is absent.

    Raises MissingData on duplicate dates (two spellings of one day).
    """
    raw = (frame or {}).get(row)
    if not isinstance(raw, dict):
        return None
    out: dict[date, float | None] = {}
    for k, v in raw.items():
        d = _parse_date(k)
        if d in out:
            raise MissingData(f"Duplicate quarter date {d} in row {row!r}")
        out[d] = _clean(v)
    return out


QUARTER_GAP_DAYS = (60, 120)


def _consecutive(dates: list[date]) -> bool:
    """True when each step between the dates is about one quarter."""
    lo, hi = QUARTER_GAP_DAYS
    return all(lo <= (b - a).days <= hi for a, b in zip(dates, dates[1:], strict=False))


def _last4(pts: list[tuple[date, float]], what: str) -> tuple[float, date]:
    """Sum of the 4 latest points; raise MissingData if they are not consecutive quarters."""
    last4 = pts[-4:]
    dates = [d for d, _ in last4]
    if not _consecutive(dates):
        raise MissingData(
            f"{what}: the 4 latest quarters with data are not consecutive "
            f"({', '.join(d.isoformat() for d in dates)}); TTM would mix years"
        )
    return sum(v for _, v in last4), dates[-1]


def _ttm(frame: dict, row: str) -> tuple[float, date] | None:
    """Sum of the 4 latest finite quarters and the latest date. None if < 4.

    Raises MissingData when those quarters are not consecutive.
    """
    s = _series(frame, row)
    if s is None:
        return None
    pts = sorted((d, v) for d, v in s.items() if v is not None)
    if len(pts) < 4:
        return None
    return _last4(pts, row)


def _latest(frame: dict, row: str) -> float | None:
    s = _series(frame, row)
    if not s:
        return None
    pts = sorted((d, v) for d, v in s.items() if v is not None)
    return pts[-1][1] if pts else None


def _ttm_fcf(cashflow: dict) -> tuple[float, date, str]:
    ocf, capex = _series(cashflow, "Operating Cash Flow"), _series(cashflow, "Capital Expenditure")
    if ocf is not None and capex is not None:
        pts = sorted(
            (d, ocf[d] - abs(capex[d]))
            for d in ocf
            if d in capex and ocf[d] is not None and capex[d] is not None
        )
        if len(pts) >= 4:
            total, end = _last4(pts, "Operating Cash Flow - |Capital Expenditure|")
            return total, end, "TTM Operating Cash Flow - |Capital Expenditure|"
    fcf = _ttm(cashflow, "Free Cash Flow")
    if fcf is not None:
        return fcf[0], fcf[1], "TTM Free Cash Flow row"
    raise MissingData(
        "Need 4 quarters of cash-flow data (Operating Cash Flow and Capital Expenditure, "
        "or Free Cash Flow); fewer found"
    )


def load_company(
    ticker: str,
    fetcher: Callable[[str], RawData] = yf_fetch,
    today: date | None = None,
    allow_stale: bool = False,
    force: bool = False,
) -> CompanyInputs:
    today = today or date.today()
    raw = fetcher(ticker)
    info = raw.get("info") or {}
    cashflow = raw.get("cashflow") or {}
    income = raw.get("income") or {}
    balance = raw.get("balance") or {}
    warnings: list[str] = []

    sector = info.get("sector")
    if sector == "Financial Services":
        if not force:
            raise FinancialsSector(
                f"{ticker}: sector is Financial Services; FCF is not meaningful for banks "
                "and insurers. Use --force to run anyway."
            )
        warnings.append("Financial Services sector: FCF is not meaningful; result is unreliable.")

    ttm_fcf, quarter_end, fcf_source = _ttm_fcf(cashflow)
    if not math.isfinite(ttm_fcf) or ttm_fcf <= 0:
        raise NegativeFCF(f"{ticker}: DCF needs positive TTM FCF (got {ttm_fcf:,.0f})")

    # price: latest finite, positive close
    prices = {}
    for k, v in (raw.get("prices") or {}).items():
        f = _clean(v)
        if f is not None and f > 0:
            prices[_parse_date(k)] = f
    if not prices:
        raise MissingData(f"{ticker}: no valid price found")
    price_date = max(prices)
    price = prices[price_date]

    # shares
    shares = _latest(balance, "Ordinary Shares Number")
    shares_source = "balance sheet: Ordinary Shares Number (latest quarter)"
    if shares is None or shares <= 0:
        shares = _clean(info.get("sharesOutstanding"))
        shares_source = "info.sharesOutstanding"
    if shares is None or shares <= 0:
        raise MissingData(f"{ticker}: no share count (Ordinary Shares Number or sharesOutstanding)")

    # freshness
    q_age = (today - quarter_end).days
    p_age = (today - price_date).days
    for label, d, age, limit in (
        ("latest quarter end", quarter_end, q_age, MAX_QUARTER_AGE_DAYS),
        ("price date", price_date, p_age, MAX_PRICE_AGE_DAYS),
    ):
        if age > limit:
            msg = f"{ticker}: {label} {d.isoformat()} is {age} days old (limit {limit})"
            if not allow_stale:
                raise StaleData(msg + ". Use --allow-stale to continue.")
            warnings.append("Stale data allowed: " + msg)

    beta = _clean(info.get("beta"))
    if beta is None:
        warnings.append("beta missing from yfinance; pass --beta.")

    # fcff fields: report only, no fallbacks applied here
    def ttm_row(row: str, label: str, absolute: bool = False) -> float | None:
        try:
            t = _ttm(income, row)
        except MissingData as e:
            warnings.append(f"{label} unusable: {e}")
            return None
        if t is None:
            warnings.append(f"{label} missing (income statement row {row!r}, need 4 quarters)")
            return None
        return abs(t[0]) if absolute else t[0]

    ttm_interest = ttm_row("Interest Expense", "TTM interest expense", absolute=True)
    ttm_tax = ttm_row("Tax Provision", "TTM tax provision")
    ttm_pretax = ttm_row("Pretax Income", "TTM pretax income")

    total_debt = _latest(balance, "Total Debt")
    if total_debt is None:
        warnings.append("Total Debt missing (balance sheet row 'Total Debt')")
    cash, cash_source = None, None
    for row in CASH_ROWS:
        v = _latest(balance, row)
        if v is not None:
            cash, cash_source = v, row
            break
    if cash is None:
        warnings.append("Cash missing (no cash row on the balance sheet)")

    return CompanyInputs(
        ticker=str(raw.get("ticker") or ticker).upper(),
        sector=sector,
        price=price,
        price_date=price_date,
        shares=shares,
        shares_source=shares_source,
        ttm_fcf=ttm_fcf,
        fcf_source=fcf_source,
        latest_quarter_end=quarter_end,
        beta=beta,
        ttm_interest=ttm_interest,
        ttm_tax_provision=ttm_tax,
        ttm_pretax_income=ttm_pretax,
        total_debt=total_debt,
        cash=cash,
        cash_source=cash_source,
        warnings=tuple(warnings),
    )
