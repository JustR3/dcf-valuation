"""Tests for dcf.model (pure math)."""

import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dcf import model
from dcf.model import (
    ImpliedResult,
    discount,
    fcff_base,
    grid,
    growth_path,
    implied_growth,
    per_share,
    wacc,
)

COMBOS = [("equity", False), ("equity", True), ("fcff", False), ("fcff", True)]

rates = st.floats(0.05, 0.15)
g_ts = st.floats(0.0, 0.03)
growths = st.floats(-0.3, 0.6)
years_st = st.integers(1, 30)
base_cfs = st.floats(1.0, 1e4)
shares_st = st.floats(1.0, 1e3)
net_debt_mult = st.floats(-5.0, 20.0)


def ps(base, g, r, g_t, years, shares, model_name, fade, net_debt):
    return per_share(base, g, r, g_t, years, shares, model_name, fade, net_debt)


# ---------------------------------------------------------------- growth_path


def test_constant_path():
    assert growth_path(0.07, 0.025, 4, fade=False) == [0.07] * 4


def test_fade_first_and_last():
    path = growth_path(0.12, 0.025, 10, fade=True)
    assert len(path) == 10
    assert path[0] == pytest.approx(0.12, abs=1e-15)
    assert path[-1] == pytest.approx(0.025, abs=1e-15)
    diffs = [b - a for a, b in zip(path, path[1:], strict=False)]
    assert all(d < 0 for d in diffs)
    assert max(diffs) - min(diffs) < 1e-12  # linear


def test_fade_one_year_is_g():
    assert growth_path(0.12, 0.025, 1, fade=True) == [0.12]


@given(g=growths, g_t=g_ts, years=years_st)
def test_fade_endpoints_property(g, g_t, years):
    path = growth_path(g, g_t, years, fade=True)
    assert path[0] == pytest.approx(g, abs=1e-12)
    if years > 1:
        assert path[-1] == pytest.approx(g_t, abs=1e-12)


# ------------------------------------------------------------ closed form


def test_closed_form_constant():
    # base=100, g=0.10, g_T=0.02, N=2, r=0.10
    # CF1=110, CF2=121; PV1=110/1.1=100, PV2=121/1.21=100 -> explicit=200
    # TV=121*1.02/(0.10-0.02)=123.42/0.08=1542.75; PV(TV)=1542.75/1.21=1275
    # total=1475
    v = discount(100.0, growth_path(0.10, 0.02, 2, fade=False), 0.10, 0.02)
    assert v.explicit_pv == pytest.approx(200.0, abs=1e-9)
    assert v.terminal_pv == pytest.approx(1275.0, abs=1e-9)
    assert v.total_pv == pytest.approx(1475.0, abs=1e-9)
    assert v.terminal_share == pytest.approx(1275.0 / 1475.0, abs=1e-9)
    assert len(v.rows) == 2


def test_closed_form_fade_two_years():
    # base=100, g=0.20, g_T=0.0, N=2 -> path [0.20, 0.0]; r=0.10
    # CF1=120, CF2=120; PV1=120/1.1=109.0909..., PV2=120/1.21=99.1735...
    # TV=120*1/(0.10-0)=1200; PV(TV)=1200/1.21=991.7355...
    # total=(132 + 120 + 1200)/1.21 = 1452/1.21 = 1200
    v = discount(100.0, growth_path(0.20, 0.0, 2, fade=True), 0.10, 0.0)
    assert v.total_pv == pytest.approx(1200.0, abs=1e-9)


def test_closed_form_fade_three_years():
    # Path fades to 0.04, but discount() gets terminal growth 0.03 on purpose: it takes the
    # path and g_T as independent inputs. base=100, g=0.10, N=3 -> path [0.10, 0.07, 0.04]; r=0.10
    # CF1=110, CF2=110*1.07=117.7, CF3=117.7*1.04=122.408
    # explicit = 110/1.1 + 117.7/1.21 + 122.408/1.331
    #          = 100 + 97.272727... + 91.966...   = 289.23966942...
    # TV=122.408*1.03/(0.10-0.03)=126.08024/0.07=1801.14628...; PV(TV)=1801.14628.../1.331=1353.22786...
    # total = 1642.46753246...
    v = discount(100.0, growth_path(0.10, 0.04, 3, fade=True), 0.10, 0.03)
    assert v.explicit_pv == pytest.approx(289.2396694214876, abs=1e-9)
    assert v.terminal_pv == pytest.approx(1353.2278630460446, abs=1e-9)
    assert v.total_pv == pytest.approx(1642.4675324675322, abs=1e-9)


def test_closed_form_per_share_both_models():
    # total PV = 1475 (see constant case). equity: 1475/10 = 147.5
    # fcff: (1475 - 275)/10 = 120
    kw = {"base_cf": 100.0, "g": 0.10, "r": 0.10, "g_t": 0.02, "years": 2, "shares": 10.0, "fade": False}
    assert per_share(model="equity", net_debt=275.0, **kw) == pytest.approx(147.5, abs=1e-9)
    assert per_share(model="fcff", net_debt=275.0, **kw) == pytest.approx(120.0, abs=1e-9)


def test_rows_sum_to_total():
    v = discount(50.0, growth_path(0.05, 0.02, 7, fade=True), 0.09, 0.02)
    assert sum(row.pv for row in v.rows) == pytest.approx(v.explicit_pv, rel=1e-12)
    assert v.explicit_pv + v.terminal_pv == pytest.approx(v.total_pv, rel=1e-12)


@given(g=st.floats(-0.3, 0.6), r=rates, g_t=g_ts, years=years_st)
def test_constant_equals_fade_when_g_is_gt(g, r, g_t, years):
    a = per_share(100.0, g_t, r, g_t, years, 10.0, "equity", False, 0.0)
    b = per_share(100.0, g_t, r, g_t, years, 10.0, "equity", True, 0.0)
    assert a == pytest.approx(b, rel=1e-12)


def test_g_equals_gt_equal_values():
    for years in (1, 2, 10):
        a = discount(100.0, growth_path(0.025, 0.025, years, False), 0.08, 0.025).total_pv
        b = discount(100.0, growth_path(0.025, 0.025, years, True), 0.08, 0.025).total_pv
        assert a == pytest.approx(b, abs=1e-9)


def test_years_one_fade_matches_constant():
    a = discount(100.0, growth_path(0.2, 0.02, 1, True), 0.08, 0.02).total_pv
    b = discount(100.0, growth_path(0.2, 0.02, 1, False), 0.08, 0.02).total_pv
    assert a == pytest.approx(b, abs=1e-12)


# ------------------------------------------------------------- fcff / wacc


def test_fcff_base():
    # 100 + 10*(1-0.25) = 107.5
    assert fcff_base(100.0, 10.0, 0.25) == pytest.approx(107.5, abs=1e-12)
    assert fcff_base(100.0, 0.0, 0.21) == 100.0


def test_wacc():
    # E=600, D=400, Ke=0.10, Kd=0.05, t=0.2
    # 0.6*0.10 + 0.4*0.05*0.8 = 0.06 + 0.016 = 0.076
    assert wacc(600.0, 400.0, 0.10, 0.05, 0.2) == pytest.approx(0.076, abs=1e-12)
    assert wacc(100.0, 0.0, 0.09, 0.05, 0.2) == pytest.approx(0.09, abs=1e-12)


# --------------------------------------------------------------- properties


@pytest.mark.parametrize(("model_name", "fade"), COMBOS)
class TestProperties:
    @settings(max_examples=60, deadline=None)
    @given(
        g=growths,
        delta=st.floats(1e-3, 0.3),
        r=rates,
        g_t=g_ts,
        years=years_st,
        base=base_cfs,
        shares=shares_st,
        nd=net_debt_mult,
    )
    def test_strictly_increasing_in_g(self, model_name, fade, g, delta, r, g_t, years, base, shares, nd):
        lo = ps(base, g, r, g_t, years, shares, model_name, fade, nd * base)
        hi = ps(base, g + delta, r, g_t, years, shares, model_name, fade, nd * base)
        assert hi > lo

    @settings(max_examples=60, deadline=None)
    @given(
        g=growths,
        r=rates,
        dr=st.floats(1e-3, 0.05),
        g_t=g_ts,
        years=years_st,
        base=base_cfs,
        shares=shares_st,
    )
    def test_decreasing_in_r(self, model_name, fade, g, r, dr, g_t, years, base, shares):
        lo_r = ps(base, g, r, g_t, years, shares, model_name, fade, 0.0)
        hi_r = ps(base, g, r + dr, g_t, years, shares, model_name, fade, 0.0)
        assert hi_r < lo_r

    @settings(max_examples=60, deadline=None)
    @given(
        g=st.floats(-0.45, 0.95),
        r=rates,
        g_t=g_ts,
        years=years_st,
        base=base_cfs,
        shares=shares_st,
        nd=net_debt_mult,
    )
    def test_round_trip(self, model_name, fade, g, r, g_t, years, base, shares, nd):
        price = ps(base, g, r, g_t, years, shares, model_name, fade, nd * base)
        res = implied_growth(price, base, r, g_t, years, shares, model_name, fade, nd * base)
        assert res.status == "ok"
        assert res.growth == pytest.approx(g, abs=1e-6)

    @settings(max_examples=60, deadline=None)
    @given(g=growths, r=rates, g_t=g_ts, years=years_st, base=base_cfs)
    def test_terminal_share_in_unit_interval(self, model_name, fade, g, r, g_t, years, base):
        v = discount(base, growth_path(g, g_t, years, fade), r, g_t)
        assert 0.0 < v.terminal_share < 1.0
        assert math.isfinite(v.total_pv)


# ------------------------------------------------------------- implied: bounds


def test_no_root_price_too_high():
    # Price far above the value at g = +100%.
    top = per_share(100.0, 1.0, 0.09, 0.025, 10, 10.0, "equity", False, 0.0)
    res = implied_growth(top * 2, 100.0, 0.09, 0.025, 10, 10.0, "equity", False, 0.0)
    assert isinstance(res, ImpliedResult)
    assert res.status == "above_upper"
    assert res.growth is None
    assert res.bound == pytest.approx(1.0)


def test_no_root_price_too_low():
    bottom = per_share(100.0, -0.5, 0.09, 0.025, 10, 10.0, "equity", False, 0.0)
    res = implied_growth(bottom / 2, 100.0, 0.09, 0.025, 10, 10.0, "equity", False, 0.0)
    assert res.status == "below_lower"
    assert res.growth is None
    assert res.bound == pytest.approx(-0.5)


def test_no_root_fcff_price_below_with_big_debt():
    # Heavy net debt makes the per-share value negative at the bottom bound; a positive
    # price above the top-of-range value still reports the upper bound.
    top = per_share(100.0, 1.0, 0.09, 0.025, 10, 10.0, "fcff", True, 5000.0)
    res = implied_growth(top + 1.0, 100.0, 0.09, 0.025, 10, 10.0, "fcff", True, 5000.0)
    assert res.status == "above_upper"


def test_root_at_bracket_edge_is_ok():
    price = per_share(100.0, 1.0, 0.09, 0.025, 10, 10.0, "equity", False, 0.0)
    res = implied_growth(price, 100.0, 0.09, 0.025, 10, 10.0, "equity", False, 0.0)
    assert res.status == "ok"
    assert res.growth == pytest.approx(1.0, abs=1e-9)


# ----------------------------------------------------------------------- grid


def test_grid_shape_and_center():
    price = per_share(100.0, 0.06, 0.09, 0.025, 10, 10.0, "equity", False, 0.0)
    cells = grid(price, 100.0, 0.09, 10, 10.0, "equity", False, 0.0)
    assert len(cells) == 15
    offsets = sorted({k[0] for k in cells})
    gts = sorted({k[1] for k in cells})
    assert offsets == [-0.02, -0.01, 0.0, 0.01, 0.02]
    assert gts == [0.015, 0.025, 0.035]
    assert cells[(0.0, 0.025)].growth == pytest.approx(0.06, abs=1e-6)
    # higher discount rate -> higher implied growth
    assert cells[(0.02, 0.025)].growth > cells[(-0.02, 0.025)].growth
    # higher terminal growth -> lower implied growth
    assert cells[(0.0, 0.035)].growth < cells[(0.0, 0.015)].growth


def test_grid_r_not_above_gt_cell_is_flagged():
    cells = grid(100.0, 100.0, 0.04, 10, 10.0, "equity", False, 0.0)
    cell = cells[(-0.02, 0.035)]  # r = 0.02 <= g_T = 0.035
    assert cell.status == "invalid"
    assert cell.growth is None


# ------------------------------------------------------------------ contracts


@pytest.mark.parametrize(
    "call",
    [
        lambda: growth_path(0.05, 0.02, 0, False),
        lambda: growth_path(0.05, 0.02, 31, False),
        lambda: growth_path(float("nan"), 0.02, 5, False),
        lambda: discount(0.0, [0.05], 0.08, 0.02),
        lambda: discount(-5.0, [0.05], 0.08, 0.02),
        lambda: discount(float("inf"), [0.05], 0.08, 0.02),
        lambda: discount(100.0, [0.05], 0.02, 0.02),
        lambda: discount(100.0, [0.05], 0.01, 0.02),
        lambda: discount(100.0, [], 0.08, 0.02),
        lambda: fcff_base(100.0, 5.0, 1.0),
        lambda: fcff_base(100.0, 5.0, -0.1),
        lambda: wacc(100.0, 50.0, 0.1, 0.05, 1.0),
        lambda: wacc(0.0, 0.0, 0.1, 0.05, 0.2),
        lambda: per_share(100.0, 0.05, 0.08, 0.02, 10, 0.0, "equity", False, 0.0),
        lambda: per_share(100.0, 0.05, 0.08, 0.02, 10, -1.0, "equity", False, 0.0),
        lambda: per_share(100.0, 0.05, 0.08, 0.02, 10, 10.0, "bogus", False, 0.0),
        lambda: implied_growth(float("nan"), 100.0, 0.08, 0.02, 10, 10.0, "equity", False, 0.0),
    ],
)
def test_contract_violations_raise_value_error(call):
    with pytest.raises(ValueError):
        call()


def test_model_module_is_pure():
    src = Path(model.__file__).read_text()
    for banned in ("import requests", "import yfinance", "import socket", "import urllib", "open("):
        assert banned not in src
