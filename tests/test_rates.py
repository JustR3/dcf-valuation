"""Offline tests for dcf.rates. FRED access is injected; no network."""

import json
from datetime import date
from pathlib import Path

import pytest
import requests

from dcf import model
from dcf.errors import DataUnavailable
from dcf.rates import (
    ERP_DEFAULT,
    KD_SPREAD,
    TAX_FALLBACK,
    MissingSecret,
    StaleRate,
    cost_of_equity,
    discount_rate,
    fcff_tax_rate,
    fred_fetch,
    require_fred_key,
    risk_free,
)

FIXTURE = Path(__file__).parent / "fixtures" / "fred_dgs10.json"
TODAY = date(2026, 10, 22)


def fetch_fixture(api_key, series="DGS10"):
    assert series == "DGS10"
    return json.loads(FIXTURE.read_text())


def fetch_with(observations):
    return lambda api_key, series="DGS10": {"observations": observations}


def obs(d, v):
    return {"date": d, "value": v}


def test_constants():
    assert (ERP_DEFAULT, KD_SPREAD, TAX_FALLBACK) == (0.05, 0.015, 0.21)


def test_risk_free_fresh_skips_dot():
    r = risk_free("k", fetch=fetch_fixture, today=TODAY)
    assert r.rate == pytest.approx(0.0425, abs=1e-15)
    assert r.obs_date == date(2026, 10, 20)
    assert "DGS10" in r.source
    assert r.warnings == ()


def test_risk_free_stale_raises_with_date():
    with pytest.raises(StaleRate, match="2026-10-20"):
        risk_free("k", fetch=fetch_fixture, today=date(2026, 11, 2))


def test_risk_free_boundary_10_days_ok():
    r = risk_free("k", fetch=fetch_fixture, today=date(2026, 10, 30))
    assert r.warnings == ()


def test_risk_free_allow_stale_warns():
    r = risk_free("k", fetch=fetch_fixture, today=date(2026, 11, 20), allow_stale=True)
    assert r.rate == pytest.approx(0.0425)
    assert len(r.warnings) == 1
    assert "2026-10-20" in r.warnings[0]


def test_risk_free_no_valid_observation():
    with pytest.raises(StaleRate):
        risk_free("k", fetch=fetch_with([obs("2026-10-21", ".")]), today=TODAY)
    with pytest.raises(StaleRate):
        risk_free("k", fetch=fetch_with([]), today=TODAY)


def test_require_fred_key():
    assert require_fred_key({"FRED_API_KEY": "abc"}) == "abc"
    for env in ({}, {"FRED_API_KEY": ""}, {"FRED_API_KEY": "  "}):
        with pytest.raises(MissingSecret) as e:
            require_fred_key(env)
        assert str(e.value) == (
            "FRED_API_KEY is not set. Add it to .env (see .env.example) or pass --rf."
        )


def test_cost_of_equity():
    assert cost_of_equity(0.04, 1.2) == pytest.approx(0.04 + 1.2 * 0.05, abs=1e-15)
    assert cost_of_equity(0.04, 1.2, erp=0.06) == pytest.approx(0.112, abs=1e-15)


COMMON = {"rf": 0.04, "beta": 1.0, "erp": 0.05, "price": 50.0, "shares": 100.0}


def test_equity_rate_is_ke():
    b = discount_rate(
        "equity", total_debt=None, ttm_interest=None, ttm_tax_provision=None,
        ttm_pretax_income=None, **COMMON,
    )
    assert b.model == "equity"
    assert b.rate == pytest.approx(0.09, abs=1e-15)
    assert b.ke == pytest.approx(0.09)
    assert b.warnings == ()


def fcff(**kw):
    args = dict(
        COMMON, model="fcff", total_debt=2000.0, ttm_interest=100.0,
        ttm_tax_provision=40.0, ttm_pretax_income=200.0,
    )
    args.update(kw)
    return discount_rate(**args)


def test_fcff_happy_path_hand_computed():
    b = fcff()
    ke, kd, t = 0.09, 100.0 / 2000.0, 0.2
    e, d = 5000.0, 2000.0
    expected = e / (e + d) * ke + d / (e + d) * kd * (1 - t)
    assert b.rate == pytest.approx(expected, abs=1e-12)
    assert b.rate == pytest.approx(model.wacc(e, d, ke, kd, t), abs=1e-12)
    assert b.kd == pytest.approx(0.05, abs=1e-15)
    assert b.tax_rate == pytest.approx(0.2, abs=1e-15)
    assert b.weight_equity == pytest.approx(5000 / 7000, abs=1e-15)
    assert b.weight_debt == pytest.approx(2000 / 7000, abs=1e-15)
    assert b.warnings == ()


@pytest.mark.parametrize("pretax", [0.0, -50.0, None, float("nan")])
def test_tax_fallback(pretax):
    b = fcff(ttm_pretax_income=pretax)
    assert b.tax_rate == 0.21
    assert any("21" in w and "tax" in w.lower() for w in b.warnings)


def test_tax_missing_provision_falls_back():
    b = fcff(ttm_tax_provision=None)
    assert b.tax_rate == 0.21
    assert b.warnings


def test_tax_clipped_with_warning():
    hi = fcff(ttm_tax_provision=400.0)
    assert hi.tax_rate == 0.99
    assert any("clip" in w.lower() for w in hi.warnings)
    lo = fcff(ttm_tax_provision=-40.0)
    assert lo.tax_rate == 0.0
    assert any("clip" in w.lower() for w in lo.warnings)


@pytest.mark.parametrize("interest", [None, float("nan")])
def test_kd_fallback_interest_missing(interest):
    b = fcff(ttm_interest=interest)
    assert b.kd == pytest.approx(0.04 + 0.015, abs=1e-15)
    assert any("Kd" in w for w in b.warnings)


def test_kd_fallback_zero_debt():
    b = fcff(total_debt=0.0)
    assert b.kd == pytest.approx(0.055)
    assert b.weight_debt == 0.0
    assert b.rate == pytest.approx(0.09, abs=1e-12)
    assert any("Kd" in w for w in b.warnings)


def test_missing_total_debt_raises():
    with pytest.raises(ValueError, match="total_debt"):
        fcff(total_debt=None)


def test_override_rate_keeps_components():
    b = fcff(override=0.08)
    assert b.rate == 0.08
    assert b.ke == pytest.approx(0.09)
    assert b.kd == pytest.approx(0.05)
    assert any("override" in w.lower() for w in b.warnings)
    e = discount_rate("equity", override=0.07, total_debt=None, ttm_interest=None,
                      ttm_tax_provision=None, ttm_pretax_income=None, **COMMON)
    assert e.rate == 0.07
    assert any("override" in w.lower() for w in e.warnings)


def test_tax_and_kd_overrides():
    b = fcff(tax_override=0.3, kd_override=0.06)
    assert b.tax_rate == 0.3
    assert b.kd == 0.06
    expected = 5000 / 7000 * 0.09 + 2000 / 7000 * 0.06 * 0.7
    assert b.rate == pytest.approx(expected, abs=1e-12)
    assert b.warnings == ()


def test_fcff_tax_rate_helper_matches():
    t, w = fcff_tax_rate(40.0, 200.0)
    assert t == pytest.approx(0.2) and w == ()
    t, w = fcff_tax_rate(40.0, -1.0)
    assert t == 0.21 and w
    t, w = fcff_tax_rate(1.0, 1.0, override=0.3)
    assert t == 0.3 and w == ()


def test_unknown_model_raises():
    with pytest.raises(ValueError):
        discount_rate("ddm", total_debt=1.0, ttm_interest=1.0, ttm_tax_provision=1.0,
                      ttm_pretax_income=1.0, **COMMON)


# ---------------------------------------------------------------- review fixes

@pytest.mark.parametrize("row", [{"value": "4.1"}, {"date": "2026-10-20"}, {}])
def test_fred_row_without_date_or_value_is_data_unavailable(row):
    with pytest.raises(DataUnavailable):
        risk_free("k", fetch=fetch_with([obs("2026-10-19", "4.0"), row]), today=TODAY)


def test_fred_payload_without_observations_list_is_data_unavailable():
    with pytest.raises(DataUnavailable):
        risk_free("k", fetch=lambda k, s="DGS10": {"error_code": 400}, today=TODAY)


class _Resp:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        raise requests.HTTPError(f"{self.status_code} Error for url: https://x/?api_key=SECRETKEY", response=self)

    def json(self):
        return {}


@pytest.mark.parametrize(
    "boom",
    [requests.ConnectionError("down api_key=SECRETKEY"), requests.Timeout("slow"), _Resp(500)],
)
def test_fred_fetch_request_errors_become_data_unavailable(monkeypatch, boom):
    def fake_get(*a, **k):
        if isinstance(boom, Exception):
            raise boom
        return boom

    monkeypatch.setattr("dcf.rates.requests.get", fake_get)
    with pytest.raises(DataUnavailable) as exc:
        fred_fetch("SECRETKEY")
    msg = str(exc.value)
    assert "FRED" in msg and "\n" not in msg and "SECRETKEY" not in msg


def test_fred_fetch_bad_json_is_data_unavailable(monkeypatch):
    class R:
        def raise_for_status(self):
            pass

        def json(self):
            raise requests.exceptions.JSONDecodeError("bad", "doc", 0)

    monkeypatch.setattr("dcf.rates.requests.get", lambda *a, **k: R())
    with pytest.raises(DataUnavailable):
        fred_fetch("k")


def _fcff(**kw):
    args = {"model": "fcff", "rf": 0.04, "beta": 1.0, "erp": 0.05, "price": 50.0, "shares": 100.0,
            "total_debt": 1000.0, "ttm_interest": 40.0, "ttm_tax_provision": 20.0,
            "ttm_pretax_income": 100.0}
    args.update(kw)
    return discount_rate(**args)


def test_kd_above_15_percent_warns():
    assert any("Kd" in w and "15" in w for w in _fcff(kd_override=0.20).warnings)
    assert any("Kd" in w and "15" in w for w in _fcff(ttm_interest=200.0).warnings)
    assert not any("15%" in w for w in _fcff(kd_override=0.15).warnings)


def test_equity_override_without_rf_has_no_ke():
    rb = discount_rate("equity", None, 1.0, 0.05, 50.0, 100.0, None, None, None, None, override=0.085)
    assert rb.rate == 0.085 and rb.ke is None
