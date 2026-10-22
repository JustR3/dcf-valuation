"""Offline tests for dcf.data. All data comes from tests/fixtures and a fixed `today`."""

from __future__ import annotations

import copy
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dcf.data import CompanyInputs, load_company
from dcf.errors import (
    DCFInputError,
    FinancialsSector,
    MissingData,
    NegativeFCF,
    StaleData,
)

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 22)


def raw_fixture(ticker: str) -> dict:
    return json.loads((FIXTURES / f"{ticker}.json").read_text())


def fixture_fetcher(ticker: str) -> dict:
    return raw_fixture(ticker)


def fetcher_for(raw: dict):
    return lambda ticker: copy.deepcopy(raw)


# ---------------------------------------------------------------- fixtures

def test_ko_ok():
    c = load_company("KO", fetcher=fixture_fetcher, today=TODAY)
    assert isinstance(c, CompanyInputs)
    assert c.ticker == "KO"
    assert c.sector == "Consumer Defensive"
    assert c.price > 0 and c.shares > 0 and c.ttm_fcf > 0
    assert c.price_date == date(2026, 10, 22)
    assert c.latest_quarter_end == date(2026, 6, 30)
    # TTM = last 4 quarters of OCF - |capex|: 2025-09 .. 2026-06
    raw = raw_fixture("KO")
    ocf, capex = raw["cashflow"]["Operating Cash Flow"], raw["cashflow"]["Capital Expenditure"]
    quarters = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    expected = sum(ocf[q] - abs(capex[q]) for q in quarters)
    assert c.ttm_fcf == pytest.approx(expected)
    assert "Operating Cash Flow" in c.fcf_source
    assert "Ordinary Shares Number" in c.shares_source
    assert c.ttm_interest is not None and c.ttm_interest > 0
    assert c.ttm_tax_provision is not None and c.ttm_pretax_income is not None
    assert c.total_debt is not None and c.total_debt > 0
    assert c.cash is not None and c.cash_source in (
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents",
    )
    assert c.warnings == ()


def test_dataclass_is_frozen():
    c = load_company("KO", fetcher=fixture_fetcher, today=TODAY)
    with pytest.raises(AttributeError):
        c.price = 1.0  # type: ignore[misc]


def test_aapl_missing_interest_gives_warning():
    c = load_company("AAPL", fetcher=fixture_fetcher, today=TODAY)
    assert c.ttm_interest is None
    assert any("interest" in w.lower() for w in c.warnings)
    assert c.ttm_fcf > 0
    assert c.total_debt is not None


def test_jpm_refused_unless_force():
    with pytest.raises(FinancialsSector):
        load_company("JPM", fetcher=fixture_fetcher, today=TODAY)
    with pytest.raises(FinancialsSector):
        load_company("JPM", fetcher=fixture_fetcher, today=TODAY, allow_stale=True)


def test_jpm_force_adds_warning():
    # JPM FCF can be negative; only the sector gate is under test here, so patch OCF positive.
    raw = raw_fixture("JPM")
    for row in ("Operating Cash Flow", "Free Cash Flow"):
        raw["cashflow"][row] = dict.fromkeys(raw["cashflow"][row], 1000000000.0)
    c = load_company("JPM", fetcher=fetcher_for(raw), today=TODAY, force=True)
    assert any("financial" in w.lower() for w in c.warnings)


def test_jpm_force_negative_fcf_still_refused():
    raw = raw_fixture("JPM")
    for row in ("Operating Cash Flow", "Free Cash Flow"):
        raw["cashflow"][row] = dict.fromkeys(raw["cashflow"][row], -1000000000.0)
    with pytest.raises(NegativeFCF):
        load_company("JPM", fetcher=fetcher_for(raw), today=TODAY, force=True)


# ---------------------------------------------------------------- freshness

def test_stale_quarter_refused_with_actual_date():
    with pytest.raises(StaleData, match="2026-06-30"):
        load_company("KO", fetcher=fixture_fetcher, today=date(2027, 1, 20))  # 204 days


def test_quarter_at_200_days_is_ok():
    today = date(2026, 6, 30) + timedelta(days=200)
    raw = raw_fixture("KO")
    raw["prices"] = {today.isoformat(): 60.0}
    c = load_company("KO", fetcher=fetcher_for(raw), today=today)
    assert c.latest_quarter_end == date(2026, 6, 30)


def test_stale_quarter_allowed_with_warning():
    c = load_company("KO", fetcher=lambda t: _with_fresh_price(raw_fixture(t), date(2027, 1, 20)),
                     today=date(2027, 1, 20), allow_stale=True)
    assert any("2026-06-30" in w for w in c.warnings)


def _with_fresh_price(raw: dict, d: date) -> dict:
    raw["prices"] = {d.isoformat(): 60.0}
    return raw


def test_stale_price_refused_with_actual_date():
    with pytest.raises(StaleData, match="2026-10-22"):
        load_company("KO", fetcher=fixture_fetcher, today=date(2026, 10, 30))  # 8 days


def test_price_at_7_days_is_ok():
    c = load_company("KO", fetcher=fixture_fetcher, today=date(2026, 10, 29))
    assert c.price_date == date(2026, 10, 22)


def test_stale_price_allowed_with_warning():
    c = load_company("KO", fetcher=fixture_fetcher, today=date(2026, 11, 15), allow_stale=True)
    assert any("2026-10-22" in w for w in c.warnings)


# ---------------------------------------------------------------- refusals

def test_missing_prices_is_missing_data():
    raw = raw_fixture("KO")
    raw["prices"] = {}
    with pytest.raises(MissingData):
        load_company("KO", fetcher=fetcher_for(raw), today=TODAY)


def test_error_hierarchy_and_exit_code():
    for exc in (NegativeFCF, FinancialsSector, StaleData, MissingData):
        assert issubclass(exc, DCFInputError)
        assert exc.exit_code == 2


def test_falls_back_to_free_cash_flow_row_when_capex_missing():
    raw = raw_fixture("KO")
    del raw["cashflow"]["Capital Expenditure"]
    c = load_company("KO", fetcher=fetcher_for(raw), today=TODAY)
    assert "Free Cash Flow" in c.fcf_source
    fcf = raw["cashflow"]["Free Cash Flow"]
    quarters = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    assert c.ttm_fcf == pytest.approx(sum(fcf[q] for q in quarters))


def test_shares_fall_back_to_info():
    raw = raw_fixture("KO")
    del raw["balance"]["Ordinary Shares Number"]
    c = load_company("KO", fetcher=fetcher_for(raw), today=TODAY)
    assert c.shares == raw["info"]["sharesOutstanding"]
    assert "sharesOutstanding" in c.shares_source


def test_no_shares_anywhere_is_missing_data():
    raw = raw_fixture("KO")
    del raw["balance"]["Ordinary Shares Number"]
    raw["info"]["sharesOutstanding"] = None
    with pytest.raises(MissingData):
        load_company("KO", fetcher=fetcher_for(raw), today=TODAY)


def test_cash_fallback_row():
    raw = raw_fixture("KO")
    del raw["balance"]["Cash Cash Equivalents And Short Term Investments"]
    c = load_company("KO", fetcher=fetcher_for(raw), today=TODAY)
    assert c.cash_source == "Cash And Cash Equivalents"


def test_missing_debt_row_is_none_with_warning():
    raw = raw_fixture("KO")
    del raw["balance"]["Total Debt"]
    c = load_company("KO", fetcher=fetcher_for(raw), today=TODAY)
    assert c.total_debt is None
    assert any("debt" in w.lower() for w in c.warnings)


def test_negative_pretax_is_reported_not_replaced():
    raw = raw_fixture("KO")
    raw["income"]["Pretax Income"] = dict.fromkeys(raw["income"]["Pretax Income"], -1.0)
    c = load_company("KO", fetcher=fetcher_for(raw), today=TODAY)
    assert c.ttm_pretax_income is not None and c.ttm_pretax_income < 0  # fallback is rates' job


# ---------------------------------------------------------------- Hypothesis

def synth(dates: list[str], ocf: list, capex: list, price_date: str = "2026-10-22") -> dict:
    return {
        "ticker": "ZZZ",
        "info": {"sector": "Technology", "beta": 1.0, "sharesOutstanding": 100.0},
        "cashflow": {
            "Operating Cash Flow": dict(zip(dates, ocf, strict=False)),
            "Capital Expenditure": dict(zip(dates, capex, strict=False)),
        },
        "income": {},
        "balance": {"Total Debt": {dates[-1] if dates else "2026-06-30": 10.0}},
        "prices": {price_date: 50.0},
    }


QUARTER_ENDS = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
cell = st.one_of(
    st.none(),
    st.just(float("nan")),
    st.just(float("inf")),
    st.floats(min_value=-1e12, max_value=1e12, allow_nan=False),
)


@settings(max_examples=150, deadline=None)
@given(
    n=st.integers(min_value=0, max_value=6),
    ocf=st.lists(cell, min_size=6, max_size=6),
    capex=st.lists(cell, min_size=6, max_size=6),
)
def test_malformed_cashflow_never_crashes_and_matches_oracle(n, ocf, capex):
    dates = QUARTER_ENDS[6 - n:]
    ocf, capex = ocf[6 - n:], capex[6 - n:]
    raw = synth(dates, ocf, capex)
    usable = [
        (i, o - abs(c))
        for i, (o, c) in enumerate(zip(ocf, capex, strict=True))
        if o is not None and c is not None and math.isfinite(o) and math.isfinite(c)
    ]
    # TTM needs the 4 latest usable quarters to be consecutive (no gap inside the year).
    contiguous = len(usable) >= 4 and usable[-1][0] - usable[-4][0] == 3
    try:
        out = load_company("ZZZ", fetcher=fetcher_for(raw), today=TODAY, allow_stale=True)
    except MissingData:
        assert not contiguous
    except NegativeFCF:
        assert contiguous and sum(v for _, v in usable[-4:]) <= 0
    except DCFInputError:
        pytest.fail("unexpected typed error")
    else:
        assert contiguous
        assert math.isfinite(out.ttm_fcf) and out.ttm_fcf > 0
        assert out.ttm_fcf == pytest.approx(sum(v for _, v in usable[-4:]))


@settings(max_examples=50, deadline=None)
@given(
    vals=st.lists(st.floats(min_value=1e6, max_value=1e10), min_size=4, max_size=4),
    dup=st.integers(min_value=0, max_value=3),
)
def test_duplicate_quarter_dates_rejected(vals, dup):
    dates = QUARTER_ENDS[2:]
    dates = list(dates)
    dates.append(dates[dup] + "T00:00:00")  # same calendar day, different spelling
    raw = synth(dates, [*vals, 1e9], [-1e6] * 5)
    with pytest.raises(MissingData, match="(?i)duplicate"):
        load_company("ZZZ", fetcher=fetcher_for(raw), today=TODAY)


@settings(max_examples=50, deadline=None)
@given(shuffle_seed=st.randoms(use_true_random=False))
def test_unsorted_input_is_sorted(shuffle_seed):
    dates = QUARTER_ENDS[:]
    vals = [float(i + 1) * 1e9 for i in range(6)]
    pairs = list(zip(dates, vals, strict=True))
    shuffle_seed.shuffle(pairs)
    raw = synth([p[0] for p in pairs], [p[1] for p in pairs], [0.0] * 6)
    out = load_company("ZZZ", fetcher=fetcher_for(raw), today=TODAY)
    assert out.ttm_fcf == pytest.approx(sum(vals[-4:]))  # latest 4 by date, not by position
    assert out.latest_quarter_end == date(2026, 6, 30)


@settings(max_examples=30, deadline=None)
@given(drop=st.sampled_from(["cashflow", "prices", "info"]))
def test_missing_top_level_sections_raise_typed_error(drop):
    raw = synth(QUARTER_ENDS, [1e9] * 6, [-1e8] * 6)
    del raw[drop]
    with pytest.raises(DCFInputError):
        load_company("ZZZ", fetcher=fetcher_for(raw), today=TODAY)


@settings(max_examples=40, deadline=None)
@given(bad=st.sampled_from([float("nan"), float("inf"), -float("inf"), 0.0, -5.0]))
def test_bad_price_rejected(bad):
    raw = synth(QUARTER_ENDS, [1e9] * 6, [-1e8] * 6)
    raw["prices"] = {"2026-10-22": bad}
    with pytest.raises(MissingData):
        load_company("ZZZ", fetcher=fetcher_for(raw), today=TODAY)


# ---------------------------------------------------------------- TTM contiguity

def test_gap_inside_ttm_window_is_missing_data():
    # 2025-12-31 is missing, so the last 4 finite quarters span 15 months.
    dates = QUARTER_ENDS[1:]
    ocf = [100.0, 100.0, None, 100.0, 100.0]
    capex = [-10.0] * 5
    with pytest.raises(MissingData, match="consecutive"):
        load_company("ZZZ", fetcher=fetcher_for(synth(dates, ocf, capex)), today=TODAY)


def test_newest_quarter_missing_uses_previous_four():
    # Newest column (2026-06-30) is empty; the 4 quarters before it are consecutive.
    dates = QUARTER_ENDS[1:]
    ocf = [100.0, 100.0, 100.0, 100.0, None]
    capex = [-10.0] * 5
    c = load_company("ZZZ", fetcher=fetcher_for(synth(dates, ocf, capex)), today=TODAY, allow_stale=True)
    assert c.latest_quarter_end == date(2026, 3, 31)
    assert c.ttm_fcf == pytest.approx(360.0)
    assert any("2026-03-31" in w for w in c.warnings)  # 205 days old: freshness still applies


def test_fcff_row_with_gap_is_none_with_warning():
    raw = raw_fixture("KO")
    interest = raw["income"]["Interest Expense"]
    second_newest = sorted(interest)[-2]
    interest[second_newest] = None
    c = load_company("KO", fetcher=fetcher_for(raw), today=TODAY)
    assert c.ttm_interest is None
    assert any("interest" in w.lower() for w in c.warnings)


# ---------------------------------------------------------------- --fcf override

def test_negative_fcf_allowed_when_caller_supplies_override():
    raw = raw_fixture("JPM")
    c = load_company("JPM", fetcher=fetcher_for(raw), today=TODAY, force=True, require_positive_fcf=False)
    assert c.ttm_fcf <= 0
    assert any("TTM FCF" in w for w in c.warnings)
