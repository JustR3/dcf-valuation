"""
FRED API Integration for Real-Time Economic Data

Fetches risk-free rate (10Y Treasury), inflation (CPI), and GDP growth
from the Federal Reserve Economic Data (FRED) API.

Requires FRED_API_KEY environment variable. Get free key at:
https://fred.stlouisfed.org/docs/api/api_key.html

Usage:
    from src.pipeline.external.fred import get_fred_connector
    
    fred = get_fred_connector()
    macro_data = fred.get_macro_data()
    print(f"Risk-free rate: {macro_data.risk_free_rate:.2%}")
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

try:
    from fredapi import Fred
    HAS_FREDAPI = True
except ImportError:
    HAS_FREDAPI = False


# Fallback risk-free rate if FRED unavailable
DEFAULT_RISK_FREE_RATE = 0.04  # 4%


@dataclass
class MacroData:
    """Container for macroeconomic indicators from FRED."""
    risk_free_rate: float
    inflation_rate: Optional[float] = None
    gdp_growth: Optional[float] = None
    source: str = "FRED"
    fetched_at: Optional[datetime] = None


class FredConnector:
    """
    FRED API connector for fetching macroeconomic data.
    
    Fetches:
    - Risk-free rate: 10-Year Treasury Constant Maturity Rate (DGS10)
    - Inflation: Consumer Price Index YoY change (CPIAUCSL)
    - GDP Growth: Real GDP annualized growth rate (A191RL1Q225SBEA)
    
    Features:
    - 24-hour caching to reduce API calls
    - Automatic fallback to DEFAULT_RISK_FREE_RATE if API unavailable
    - Graceful degradation if fredapi library not installed
    
    Example:
        connector = FredConnector()
        macro = connector.get_macro_data()
        rf_rate = macro.risk_free_rate  # decimal (e.g., 0.0416 for 4.16%)
    """
    
    def __init__(self, cache_hours: int = 24):
        """
        Initialize FRED connector.
        
        Args:
            cache_hours: Hours to cache macro data (default: 24)
        """
        self.cache_hours = cache_hours
        self._cached_data: Optional[MacroData] = None
        self._cache_timestamp: Optional[datetime] = None
        
        # Initialize FRED API client
        api_key = os.getenv("FRED_API_KEY")
        
        if not HAS_FREDAPI:
            print("⚠️  fredapi library not installed. Run: pip install fredapi")
            print(f"   Using fallback risk-free rate: {DEFAULT_RISK_FREE_RATE:.2%}")
            self.fred = None
        elif not api_key:
            print("⚠️  FRED_API_KEY not found in environment variables")
            print("   Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html")
            print(f"   Using fallback risk-free rate: {DEFAULT_RISK_FREE_RATE:.2%}")
            self.fred = None
        else:
            try:
                self.fred = Fred(api_key=api_key)
            except Exception as e:
                print(f"⚠️  Failed to initialize FRED API: {e}")
                print(f"   Using fallback risk-free rate: {DEFAULT_RISK_FREE_RATE:.2%}")
                self.fred = None
    
    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if self._cached_data is None or self._cache_timestamp is None:
            return False
        
        elapsed_hours = (datetime.now() - self._cache_timestamp).total_seconds() / 3600
        return elapsed_hours < self.cache_hours
    
    def get_risk_free_rate(self) -> float:
        """
        Fetch current 10-Year Treasury rate.
        
        Returns:
            Risk-free rate as decimal (e.g., 0.0416 for 4.16%)
        """
        macro_data = self.get_macro_data()
        return macro_data.risk_free_rate
    
    def get_macro_data(self) -> MacroData:
        """
        Fetch comprehensive macroeconomic data from FRED.
        
        Returns:
            MacroData object with risk_free_rate, inflation_rate, gdp_growth
        """
        # Return cached data if valid
        if self._is_cache_valid():
            return self._cached_data
        
        # Fallback if FRED not available
        if self.fred is None:
            return MacroData(
                risk_free_rate=DEFAULT_RISK_FREE_RATE,
                source="Fallback (FRED unavailable)",
                fetched_at=datetime.now()
            )
        
        try:
            # Fetch 10-Year Treasury rate (DGS10)
            dgs10_series = self.fred.get_series("DGS10", observation_start="2020-01-01")
            risk_free_rate = float(dgs10_series.iloc[-1]) / 100.0  # Convert percentage to decimal
            
            # Fetch CPI for inflation (optional)
            inflation_rate = None
            try:
                cpi_series = self.fred.get_series("CPIAUCSL", observation_start="2020-01-01")
                # Calculate YoY change
                current_cpi = float(cpi_series.iloc[-1])
                year_ago_cpi = float(cpi_series.iloc[-13])  # ~12 months ago
                inflation_rate = (current_cpi - year_ago_cpi) / year_ago_cpi
            except Exception:
                pass  # Inflation is optional
            
            # Fetch GDP growth (optional)
            gdp_growth = None
            try:
                gdp_series = self.fred.get_series("A191RL1Q225SBEA")  # Real GDP growth (annualized)
                gdp_growth = float(gdp_series.iloc[-1]) / 100.0  # Convert percentage to decimal
            except Exception:
                pass  # GDP is optional
            
            # Cache the result
            macro_data = MacroData(
                risk_free_rate=risk_free_rate,
                inflation_rate=inflation_rate,
                gdp_growth=gdp_growth,
                source="FRED",
                fetched_at=datetime.now()
            )
            
            self._cached_data = macro_data
            self._cache_timestamp = datetime.now()
            
            return macro_data
            
        except Exception as e:
            print(f"⚠️  FRED API error: {e}")
            print(f"   Using fallback risk-free rate: {DEFAULT_RISK_FREE_RATE:.2%}")
            return MacroData(
                risk_free_rate=DEFAULT_RISK_FREE_RATE,
                source="Fallback (FRED error)",
                fetched_at=datetime.now()
            )


# Global singleton instance
_fred_connector_instance: Optional[FredConnector] = None


def get_fred_connector() -> FredConnector:
    """
    Get singleton FredConnector instance.
    
    Returns:
        Shared FredConnector instance with 24-hour caching
    """
    global _fred_connector_instance
    if _fred_connector_instance is None:
        _fred_connector_instance = FredConnector(cache_hours=24)
    return _fred_connector_instance
