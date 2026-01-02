"""Market Regime Detection - SPY 200-SMA + VIX Term Structure Analysis.

Also includes:
- Dynamic risk-free rate fetching (10-year Treasury yield)
- Shiller CAPE ratio for macro market valuation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

import pandas as pd
import yfinance as yf

from src.config import config
from src.utils import default_cache, rate_limiter


class MarketRegime(Enum):
    """Market regime states."""
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    CAUTION = "CAUTION"
    UNKNOWN = "UNKNOWN"

    def __str__(self) -> str:
        return self.value

    @property
    def is_bullish(self) -> bool:
        return self == MarketRegime.RISK_ON


@dataclass
class VixTermStructure:
    """VIX term structure data."""
    vix9d: float
    vix: float
    vix3m: float

    @property
    def is_backwardation(self) -> bool:
        return self.vix9d > self.vix

    @property
    def is_contango(self) -> bool:
        return self.vix9d < self.vix < self.vix3m

    def to_dict(self) -> dict:
        return {
            "vix9d": self.vix9d, "vix": self.vix, "vix3m": self.vix3m,
            "is_backwardation": self.is_backwardation, "is_contango": self.is_contango,
        }


@dataclass
class RegimeResult:
    """Regime detection result with metadata."""
    regime: MarketRegime
    method: str
    last_updated: datetime
    current_price: float | None = None
    sma_200: float | None = None
    sma_signal_strength: float | None = None
    vix_structure: VixTermStructure | None = None
    vix_regime: MarketRegime | None = None

    def __str__(self) -> str:
        parts = [f"Regime: {self.regime.value}"]
        if self.current_price:
            parts.append(f"SPY: ${self.current_price:.2f}")
        if self.vix_structure:
            parts.append(f"VIX: {self.vix_structure.vix:.2f}")
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "regime": self.regime.value,
            "method": self.method,
            "last_updated": self.last_updated.isoformat(),
        }
        if self.current_price:
            result["spy"] = {"price": self.current_price, "sma_200": self.sma_200,
                            "signal_strength": self.sma_signal_strength}
        if self.vix_structure:
            result["vix"] = self.vix_structure.to_dict()
        return result


class RegimeDetector:
    """Market regime detector using SPY 200-SMA and VIX term structure."""

    def __init__(self, ticker: str = "SPY", lookback_days: int = 300,
                 cache_duration: int = 3600, use_vix: bool = True):
        self.ticker = ticker.upper()
        self.lookback_days = lookback_days
        self.cache_duration = cache_duration
        self.use_vix = use_vix
        self._cached_result: RegimeResult | None = None
        self._cache_timestamp: datetime | None = None
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _is_cache_valid(self) -> bool:
        if not self._cached_result or not self._cache_timestamp:
            return False
        return (datetime.now() - self._cache_timestamp).total_seconds() < self.cache_duration

    def _get_spy_history(self, ticker: str, lookback_days: int) -> pd.DataFrame | None:
        """Fetch SPY data with caching."""
        cache_key = f"spy_history_{ticker}_{lookback_days}"
        cached = default_cache.get(cache_key, expiry_hours=1)  # 1 hour cache for market data

        if cached is not None:
            return cached

        # Fetch from API
        try:
            data = yf.Ticker(ticker).history(
                start=datetime.now() - timedelta(days=lookback_days),
                end=datetime.now()
            )
            if not data.empty:
                default_cache.set(cache_key, data)
            return data if not data.empty else None
        except Exception:
            return None

    @rate_limiter
    def _fetch_spy_data(self) -> pd.DataFrame | None:
        try:
            data = self._get_spy_history(self.ticker, self.lookback_days)
            if data is None:
                self._last_error = f"No data for {self.ticker}"
                return None
            return data
        except Exception as e:
            self._last_error = f"Error fetching {self.ticker}: {e}"
            return None

    def _get_vix_data(self) -> pd.DataFrame | None:
        """Fetch VIX term structure with caching."""
        cache_key = "vix_term_structure"
        cached = default_cache.get(cache_key, expiry_hours=1)  # 1 hour cache

        if cached is not None:
            return cached

        # Fetch from API
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                data = yf.download(['^VIX9D', '^VIX', '^VIX3M'], period='5d', progress=False)
            if data is not None and not data.empty:
                default_cache.set(cache_key, data)
            return data
        except Exception:
            return None

    @rate_limiter
    def _fetch_vix_term_structure(self) -> VixTermStructure | None:
        try:
            data = self._get_vix_data()
            if data is None or data.empty or 'Close' not in data.columns:
                return None
            close = data['Close']
            return VixTermStructure(
                vix9d=float(close['^VIX9D'].dropna().iloc[-1]),
                vix=float(close['^VIX'].dropna().iloc[-1]),
                vix3m=float(close['^VIX3M'].dropna().iloc[-1]),
            )
        except Exception:
            return None

    def _get_vix_regime(self, vix: VixTermStructure) -> MarketRegime:
        if vix.is_backwardation:
            return MarketRegime.RISK_OFF
        if vix.vix > vix.vix3m:
            return MarketRegime.CAUTION
        return MarketRegime.RISK_ON

    def _calculate_sma_regime(self, data: pd.DataFrame) -> tuple[MarketRegime, float, float, float]:
        if len(data) < 200:
            raise ValueError(f"Need 200+ days, got {len(data)}")

        sma_200 = float(data['Close'].rolling(window=200).mean().iloc[-1])
        current = float(data['Close'].iloc[-1])
        regime = MarketRegime.RISK_ON if current > sma_200 else MarketRegime.RISK_OFF
        strength = ((current - sma_200) / sma_200) * 100
        return regime, current, sma_200, strength

    def _combine_regimes(self, sma: MarketRegime, vix: MarketRegime) -> MarketRegime:
        if vix == MarketRegime.RISK_OFF:
            return MarketRegime.RISK_OFF
        if sma == MarketRegime.RISK_ON and vix == MarketRegime.RISK_ON:
            return MarketRegime.RISK_ON
        return MarketRegime.CAUTION

    def get_regime_with_details(self, use_cache: bool = True,
                                 method: str = "combined") -> RegimeResult | None:
        if use_cache and self._is_cache_valid():
            return self._cached_result

        try:
            if method == "vix":
                vix = self._fetch_vix_term_structure()
                if not vix:
                    return None
                result = RegimeResult(
                    regime=self._get_vix_regime(vix), method="vix",
                    vix_structure=vix, vix_regime=self._get_vix_regime(vix),
                    last_updated=datetime.now(),
                )
            elif method == "sma":
                spy = self._fetch_spy_data()
                if spy is None:
                    return None
                regime, price, sma, strength = self._calculate_sma_regime(spy)
                result = RegimeResult(
                    regime=regime, method="sma", current_price=price,
                    sma_200=sma, sma_signal_strength=strength,
                    last_updated=datetime.now(),
                )
            else:  # combined
                spy = self._fetch_spy_data()
                vix = self._fetch_vix_term_structure()

                if spy is None and vix is None:
                    return None

                sma_regime, price, sma, strength = (None, None, None, None)
                if spy is not None:
                    try:
                        sma_regime, price, sma, strength = self._calculate_sma_regime(spy)
                    except ValueError:
                        pass

                vix_regime = self._get_vix_regime(vix) if vix else None

                if sma_regime and vix_regime:
                    combined = self._combine_regimes(sma_regime, vix_regime)
                else:
                    combined = vix_regime or sma_regime or MarketRegime.UNKNOWN

                result = RegimeResult(
                    regime=combined, method="combined", current_price=price,
                    sma_200=sma, sma_signal_strength=strength,
                    vix_structure=vix, vix_regime=vix_regime,
                    last_updated=datetime.now(),
                )

            self._cached_result = result
            self._cache_timestamp = datetime.now()
            return result
        except Exception as e:
            self._last_error = f"Error calculating regime: {e}"
            return None

    def get_current_regime(self, use_cache: bool = True,
                           method: str = "combined") -> MarketRegime:
        result = self.get_regime_with_details(use_cache=use_cache, method=method)
        return result.regime if result else MarketRegime.UNKNOWN

    def is_risk_on(self, use_cache: bool = True, method: str = "combined") -> bool:
        return self.get_current_regime(use_cache, method) == MarketRegime.RISK_ON

    def is_risk_off(self, use_cache: bool = True, method: str = "combined") -> bool:
        return self.get_current_regime(use_cache, method) == MarketRegime.RISK_OFF

    def clear_cache(self) -> None:
        self._cached_result = None
        self._cache_timestamp = None


# ============================================================================
# Risk-Free Rate & CAPE Macro Valuation Functions
# ============================================================================

@rate_limiter
def get_10year_treasury_yield() -> float | None:
    """Fetch current 10-year Treasury yield as risk-free rate.
    
    Data source priority:
    1. FRED API (authoritative, requires API key)
    2. yfinance ^TNX (fallback)
    3. Config default (last resort)
    
    Returns:
        Current 10-year Treasury yield as decimal (e.g., 0.045 for 4.5%)
        Falls back to config default if all sources fail.
    """
    cache_key = "treasury_10y_yield"
    cached = default_cache.get(cache_key, expiry_hours=config.MARKET_DATA_CACHE_HOURS)
    
    if cached is not None:
        return cached
    
    # Priority 1: Try FRED API (authoritative source)
    try:
        from src.external.fred import get_fred_connector
        fred = get_fred_connector()
        if fred.fred is not None:  # FRED API available
            macro_data = fred.get_macro_data()
            if macro_data and macro_data.risk_free_rate:
                rf_rate = macro_data.risk_free_rate
                if 0.0 <= rf_rate <= 0.15:  # Sanity check
                    default_cache.set(cache_key, rf_rate)
                    return rf_rate
    except Exception:
        pass
    
    # Priority 2: Fallback to yfinance ^TNX
    try:
        treasury = yf.Ticker("^TNX")
        data = treasury.history(period="5d")
        
        if data is not None and not data.empty and 'Close' in data:
            # ^TNX returns yield in percentage points (e.g., 4.5), convert to decimal
            yield_pct = float(data['Close'].iloc[-1])
            yield_decimal = yield_pct / 100.0
            
            # Sanity check: Treasury yield should be between 0% and 15%
            if 0.0 <= yield_decimal <= 0.15:
                default_cache.set(cache_key, yield_decimal)
                return yield_decimal
                
    except Exception:
        pass
    
    # Priority 3: Fallback to config default
    return config.RISK_FREE_RATE


@dataclass
class CapeData:
    """Shiller CAPE (Cyclically Adjusted PE) ratio data."""
    cape_ratio: float
    last_updated: datetime
    market_state: str  # "CHEAP", "FAIR", "EXPENSIVE"
    
    def to_dict(self) -> dict:
        return {
            "cape_ratio": self.cape_ratio,
            "last_updated": self.last_updated.isoformat(),
            "market_state": self.market_state,
        }


@rate_limiter  
def get_current_cape() -> CapeData | None:
    """Fetch current Shiller CAPE ratio for market valuation assessment.
    
    Data source priority:
    1. Yale Shiller dataset (authoritative, via src/external/shiller.py)
    2. yfinance SPY/^GSPC PE ratio estimate (fallback)
    3. Conservative default (last resort)
    
    The CAPE ratio uses 10-year inflation-adjusted earnings to smooth out
    business cycle fluctuations. Historical average is ~16-17.
    
    Returns:
        CapeData object with current CAPE and market state classification
        None if all sources fail
    """
    cache_key = "shiller_cape"
    cached = default_cache.get(cache_key, expiry_hours=config.CAPE_CACHE_HOURS)
    
    # Reconstruct CapeData from cached dict
    if cached is not None and isinstance(cached, dict):
        try:
            return CapeData(
                cape_ratio=cached['cape_ratio'],
                last_updated=datetime.fromisoformat(cached['last_updated']),
                market_state=cached['market_state']
            )
        except Exception:
            pass
    
    # Priority 1: Try Yale Shiller dataset (authoritative source)
    try:
        from src.external.shiller import get_current_cape as get_shiller_cape
        shiller_cape = get_shiller_cape()
        
        if shiller_cape and 5 < shiller_cape < 100:  # Sanity check
            # Classify market state based on historical CAPE ranges
            if shiller_cape < config.CAPE_LOW_THRESHOLD:
                market_state = "CHEAP"
            elif shiller_cape > config.CAPE_HIGH_THRESHOLD:
                market_state = "EXPENSIVE"
            else:
                market_state = "FAIR"
            
            cape_data = CapeData(
                cape_ratio=shiller_cape,
                last_updated=datetime.now(),
                market_state=market_state
            )
            default_cache.set(cache_key, cape_data.to_dict())
            return cape_data
    except Exception:
        pass
    
    # Priority 2: Fallback to yfinance PE ratio estimate
    try:
        # Try SPY ETF (more reliable than ^GSPC)
        spy = yf.Ticker("SPY")
        spy_info = spy.info
        pe_ratio = spy_info.get('trailingPE')
        
        # If SPY fails, try S&P 500 index
        if not pe_ratio or pe_ratio <= 0:
            sp500 = yf.Ticker("^GSPC")
            sp500_info = sp500.info
            pe_ratio = sp500_info.get('trailingPE')
        
        # Use forward PE if trailing not available
        if not pe_ratio or pe_ratio <= 0:
            pe_ratio = spy_info.get('forwardPE') or sp500_info.get('forwardPE')
        
        if pe_ratio and 5 < pe_ratio < 100:  # Sanity check
            # CAPE is typically 15-30% higher than TTM PE (due to smoothing)
            cape_estimate = pe_ratio * 1.2
            
            if cape_estimate < config.CAPE_LOW_THRESHOLD:
                market_state = "CHEAP"
            elif cape_estimate > config.CAPE_HIGH_THRESHOLD:
                market_state = "EXPENSIVE"
            else:
                market_state = "FAIR"
            
            cape_data = CapeData(
                cape_ratio=cape_estimate,
                last_updated=datetime.now(),
                market_state=market_state
            )
            default_cache.set(cache_key, cape_data.to_dict())
            return cape_data
            
    except Exception:
        pass
    
    # Priority 3: Return a reasonable default based on recent market conditions
    try:
        fallback_cape = 25.0  # Moderate valuation
        cape_data = CapeData(
            cape_ratio=fallback_cape,
            last_updated=datetime.now(),
            market_state="FAIR"
        )
        return cape_data
    except Exception:
        return None


def calculate_cape_wacc_adjustment() -> float:
    """Calculate WACC adjustment based on Shiller CAPE market valuation.
    
    Logic:
    - CHEAP market (CAPE < 15): Lower discount rate (market undervalued, less risk premium)
    - EXPENSIVE market (CAPE > 35): Higher discount rate (market overvalued, more risk premium)
    - FAIR market: No adjustment
    
    Returns:
        WACC adjustment in percentage points (e.g., -0.005 for -50bps, +0.01 for +100bps)
    """
    if not config.ENABLE_MACRO_ADJUSTMENT:
        return 0.0
    
    cape_data = get_current_cape()
    if cape_data is None:
        return 0.0
    
    cape = cape_data.cape_ratio
    
    # Cheap market: Reduce WACC by up to 50bps (lower risk premium justified)
    if cape < config.CAPE_LOW_THRESHOLD:
        # Scale linearly: CAPE 10 → -50bps, CAPE 15 → 0bps
        adjustment = -0.005 * (config.CAPE_LOW_THRESHOLD - cape) / 5
        return max(adjustment, -0.005)  # Cap at -50bps
    
    # Expensive market: Increase WACC by up to 100bps (higher risk premium)
    elif cape > config.CAPE_HIGH_THRESHOLD:
        # Scale linearly: CAPE 35 → 0bps, CAPE 45 → +100bps
        adjustment = 0.01 * (cape - config.CAPE_HIGH_THRESHOLD) / 10
        return min(adjustment, 0.01)  # Cap at +100bps
    
    # Fair valuation: No adjustment
    return 0.0


def get_dynamic_risk_free_rate() -> tuple[float, str]:
    """Get dynamic risk-free rate with source info.
    
    Returns:
        (risk_free_rate, source_message)
    """
    rf_rate = get_10year_treasury_yield()
    
    if rf_rate and rf_rate != config.RISK_FREE_RATE:
        return rf_rate, f"10Y Treasury: {rf_rate*100:.2f}%"
    else:
        return config.RISK_FREE_RATE, f"Static (config): {config.RISK_FREE_RATE*100:.2f}%"
