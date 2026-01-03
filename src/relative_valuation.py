"""Relative Valuation Module - P/E, P/B, EV/EBITDA Analysis.

Complements DCF analysis with market-based valuation multiples to provide
triangulated view of stock value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from src.logging_config import get_logger

logger = get_logger(__name__)


# Sector-specific multiple benchmarks (derived from Damodaran + market averages)
SECTOR_PE_BENCHMARKS = {
    "Technology": 28.0,
    "Communication Services": 22.0,
    "Healthcare": 20.0,
    "Consumer Cyclical": 18.0,
    "Consumer Defensive": 20.0,
    "Industrials": 18.0,
    "Financial Services": 12.0,
    "Energy": 10.0,
    "Utilities": 15.0,
    "Real Estate": 25.0,
    "Basic Materials": 14.0,
}

SECTOR_PB_BENCHMARKS = {
    "Technology": 8.0,
    "Communication Services": 5.0,
    "Healthcare": 4.0,
    "Consumer Cyclical": 3.5,
    "Consumer Defensive": 5.0,
    "Industrials": 3.0,
    "Financial Services": 1.5,  # Banks trade close to book
    "Energy": 1.8,
    "Utilities": 2.0,
    "Real Estate": 1.5,  # REITs trade close to NAV
    "Basic Materials": 2.0,
}

SECTOR_EV_EBITDA_BENCHMARKS = {
    "Technology": 22.0,
    "Communication Services": 18.0,
    "Healthcare": 16.0,
    "Consumer Cyclical": 12.0,
    "Consumer Defensive": 14.0,
    "Industrials": 12.0,
    "Financial Services": 10.0,
    "Energy": 8.0,
    "Utilities": 10.0,
    "Real Estate": 16.0,
    "Basic Materials": 9.0,
}

# Default benchmarks for unknown sectors
DEFAULT_PE = 18.0
DEFAULT_PB = 3.0
DEFAULT_EV_EBITDA = 14.0


@dataclass
class RelativeMetrics:
    """Relative valuation metrics with sector comparison."""
    
    ticker: str
    sector: str | None
    
    # Raw multiples from yfinance
    forward_pe: float | None = None
    trailing_pe: float | None = None
    pb_ratio: float | None = None
    ev_ebitda: float | None = None
    
    # Sector benchmarks
    sector_median_pe: float | None = None
    sector_median_pb: float | None = None
    sector_median_ev_ebitda: float | None = None
    
    # Premium/discount vs sector
    pe_premium: float | None = None  # % premium/discount
    pb_premium: float | None = None
    ev_ebitda_premium: float | None = None
    
    # Classification signals
    pe_signal: str = "N/A"
    pb_signal: str = "N/A"
    ev_ebitda_signal: str = "N/A"
    
    # Composite relative score (0-100, higher = more attractive)
    relative_score: float | None = None
    overall_signal: str = "N/A"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ticker": self.ticker,
            "sector": self.sector,
            "multiples": {
                "forward_pe": round(self.forward_pe, 2) if self.forward_pe else None,
                "trailing_pe": round(self.trailing_pe, 2) if self.trailing_pe else None,
                "pb_ratio": round(self.pb_ratio, 2) if self.pb_ratio else None,
                "ev_ebitda": round(self.ev_ebitda, 2) if self.ev_ebitda else None,
            },
            "sector_benchmarks": {
                "median_pe": round(self.sector_median_pe, 2) if self.sector_median_pe else None,
                "median_pb": round(self.sector_median_pb, 2) if self.sector_median_pb else None,
                "median_ev_ebitda": round(self.sector_median_ev_ebitda, 2) if self.sector_median_ev_ebitda else None,
            },
            "premiums": {
                "pe_premium": round(self.pe_premium, 1) if self.pe_premium else None,
                "pb_premium": round(self.pb_premium, 1) if self.pb_premium else None,
                "ev_ebitda_premium": round(self.ev_ebitda_premium, 1) if self.ev_ebitda_premium else None,
            },
            "signals": {
                "pe_signal": self.pe_signal,
                "pb_signal": self.pb_signal,
                "ev_ebitda_signal": self.ev_ebitda_signal,
                "overall_signal": self.overall_signal,
            },
            "relative_score": round(self.relative_score, 1) if self.relative_score else None,
        }


class RelativeValuationEngine:
    """Calculate and analyze relative valuation multiples."""
    
    def __init__(self, ticker: str, sector: str | None = None):
        self.ticker = ticker
        self.sector = sector
    
    def analyze(
        self,
        forward_pe: float | None,
        trailing_pe: float | None,
        pb_ratio: float | None,
        ev_ebitda: float | None,
    ) -> RelativeMetrics:
        """
        Analyze relative valuation metrics with sector comparison.
        
        Args:
            forward_pe: Forward P/E ratio
            trailing_pe: Trailing P/E ratio
            pb_ratio: Price-to-Book ratio
            ev_ebitda: EV/EBITDA multiple
            
        Returns:
            RelativeMetrics with signals and scores
        """
        # Get sector benchmarks
        sector_median_pe = self._get_sector_benchmark(SECTOR_PE_BENCHMARKS, DEFAULT_PE)
        sector_median_pb = self._get_sector_benchmark(SECTOR_PB_BENCHMARKS, DEFAULT_PB)
        sector_median_ev_ebitda = self._get_sector_benchmark(SECTOR_EV_EBITDA_BENCHMARKS, DEFAULT_EV_EBITDA)
        
        # Calculate premiums/discounts
        pe_premium = self._calculate_premium(forward_pe, sector_median_pe)
        pb_premium = self._calculate_premium(pb_ratio, sector_median_pb)
        ev_ebitda_premium = self._calculate_premium(ev_ebitda, sector_median_ev_ebitda)
        
        # Generate signals
        pe_signal = self._classify_multiple(pe_premium, "P/E")
        pb_signal = self._classify_multiple(pb_premium, "P/B")
        ev_ebitda_signal = self._classify_multiple(ev_ebitda_premium, "EV/EBITDA")
        
        # Calculate composite score
        relative_score = self._calculate_relative_score(pe_premium, pb_premium, ev_ebitda_premium)
        overall_signal = self._classify_overall(relative_score)
        
        return RelativeMetrics(
            ticker=self.ticker,
            sector=self.sector,
            forward_pe=forward_pe,
            trailing_pe=trailing_pe,
            pb_ratio=pb_ratio,
            ev_ebitda=ev_ebitda,
            sector_median_pe=sector_median_pe,
            sector_median_pb=sector_median_pb,
            sector_median_ev_ebitda=sector_median_ev_ebitda,
            pe_premium=pe_premium,
            pb_premium=pb_premium,
            ev_ebitda_premium=ev_ebitda_premium,
            pe_signal=pe_signal,
            pb_signal=pb_signal,
            ev_ebitda_signal=ev_ebitda_signal,
            relative_score=relative_score,
            overall_signal=overall_signal,
        )
    
    def _get_sector_benchmark(self, benchmarks: dict, default: float) -> float:
        """Get sector benchmark or default."""
        if not self.sector:
            return default
        return benchmarks.get(self.sector, default)
    
    def _calculate_premium(self, actual: float | None, benchmark: float) -> float | None:
        """Calculate % premium/discount to benchmark."""
        if actual is None or actual <= 0:
            return None
        return ((actual - benchmark) / benchmark) * 100
    
    def _classify_multiple(self, premium: float | None, metric_name: str) -> str:
        """
        Classify valuation based on premium/discount.
        
        Logic:
        - More than 30% discount = VERY CHEAP
        - 15-30% discount = CHEAP
        - ±15% = FAIRLY VALUED
        - 15-30% premium = EXPENSIVE
        - More than 30% premium = VERY EXPENSIVE
        """
        if premium is None:
            return "N/A"
        
        if premium < -30:
            return "VERY CHEAP"
        elif premium < -15:
            return "CHEAP"
        elif premium < 15:
            return "FAIRLY VALUED"
        elif premium < 30:
            return "EXPENSIVE"
        else:
            return "VERY EXPENSIVE"
    
    def _calculate_relative_score(
        self,
        pe_premium: float | None,
        pb_premium: float | None,
        ev_ebitda_premium: float | None,
    ) -> float | None:
        """
        Calculate composite relative valuation score (0-100).
        
        Higher score = more attractive (cheaper) relative to sector.
        Score = 50 - (average_premium / 2)
        
        Examples:
        - 30% discount → score = 65 (attractive)
        - 0% premium → score = 50 (fair)
        - 30% premium → score = 35 (expensive)
        """
        premiums = [p for p in [pe_premium, pb_premium, ev_ebitda_premium] if p is not None]
        
        if not premiums:
            return None
        
        avg_premium = np.mean(premiums)
        
        # Convert premium to score (inverted: lower premium = higher score)
        score = 50 - (avg_premium / 2)
        
        # Cap at 0-100 range
        return max(0, min(100, score))
    
    def _classify_overall(self, score: float | None) -> str:
        """Classify overall relative valuation."""
        if score is None:
            return "N/A"
        
        if score >= 65:
            return "UNDERVALUED"
        elif score >= 45:
            return "FAIRLY VALUED"
        else:
            return "OVERVALUED"


def calculate_implied_fair_value(
    current_price: float,
    forward_pe: float | None,
    sector_median_pe: float,
    pb_ratio: float | None,
    sector_median_pb: float,
    ev_ebitda: float | None,
    sector_median_ev_ebitda: float,
) -> dict[str, float]:
    """
    Calculate implied fair value if stock traded at sector median multiples.
    
    This provides a "relative valuation" estimate independent of DCF.
    
    Returns:
        Dict with {pe_implied, pb_implied, ev_ebitda_implied, average_implied}
    """
    implied_values = []
    result = {}
    
    # P/E-implied value
    if forward_pe and forward_pe > 0:
        pe_implied = current_price * (sector_median_pe / forward_pe)
        result["pe_implied"] = pe_implied
        implied_values.append(pe_implied)
    
    # P/B-implied value
    if pb_ratio and pb_ratio > 0:
        pb_implied = current_price * (sector_median_pb / pb_ratio)
        result["pb_implied"] = pb_implied
        implied_values.append(pb_implied)
    
    # EV/EBITDA-implied value
    if ev_ebitda and ev_ebitda > 0:
        ev_implied = current_price * (sector_median_ev_ebitda / ev_ebitda)
        result["ev_ebitda_implied"] = ev_implied
        implied_values.append(ev_implied)
    
    # Average of all methods
    if implied_values:
        result["average_implied"] = np.mean(implied_values)
    
    return result
