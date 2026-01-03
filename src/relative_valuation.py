"""Relative Valuation Module - P/E, P/B, EV/EBITDA, PEG Analysis.

Complements DCF analysis with market-based valuation multiples to provide
triangulated view of stock value.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from src.config import config, SECTOR_PEERS
from src.logging_config import get_logger
from src.utils import default_cache

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


def get_live_peer_multiples(sector: str, exclude_ticker: str | None = None) -> dict[str, Any]:
    """
    Fetch live valuation multiples from sector peers.
    
    Uses parallel fetching and caching for performance.
    
    Args:
        sector: Sector name (e.g., "Technology")
        exclude_ticker: Ticker to exclude from peers (the stock being analyzed)
        
    Returns:
        Dict with {
            'median_pe': float,
            'median_pb': float,
            'median_ev_ebitda': float,
            'pe_range': (min, max),
            'pb_range': (min, max),
            'ev_range': (min, max),
            'peer_count': int,
            'data_quality': float (0-1)
        }
    """
    # Check cache first (24 hour expiry)
    cache_key = f"peer_multiples_{sector}_{exclude_ticker or 'all'}"
    cached = default_cache.get(cache_key)
    if cached is not None:
        logger.info(f"Using cached peer multiples for {sector}")
        return cached
    
    # Get peer list
    peers = SECTOR_PEERS.get(sector, [])
    
    if not peers:
        logger.warning(f"No peer list for sector: {sector}")
        return _empty_peer_stats()
    
    # Exclude the analyzed ticker from peers
    if exclude_ticker:
        peers = [p for p in peers if p.upper() != exclude_ticker.upper()]
    
    if not peers:
        return _empty_peer_stats()
    
    # Fetch peer data using parallel fetching (already implemented in DCFEngine)
    try:
        from src.dcf_engine import DCFEngine
        
        logger.info(f"Fetching multiples for {len(peers)} peers in {sector}...")
        peer_data = DCFEngine.fetch_batch_data(peers, show_progress=False)
        
        # Extract multiples
        peer_pes = []
        peer_pbs = []
        peer_evs = []
        
        for ticker, data in peer_data.items():
            if data:
                if data.forward_pe and data.forward_pe > 0:
                    peer_pes.append(data.forward_pe)
                if data.pb_ratio and data.pb_ratio > 0:
                    peer_pbs.append(data.pb_ratio)
                if data.ev_ebitda and data.ev_ebitda > 0:
                    peer_evs.append(data.ev_ebitda)
        
        # Calculate statistics
        result = {
            'median_pe': float(np.median(peer_pes)) if peer_pes else None,
            'median_pb': float(np.median(peer_pbs)) if peer_pbs else None,
            'median_ev_ebitda': float(np.median(peer_evs)) if peer_evs else None,
            'pe_range': (float(min(peer_pes)), float(max(peer_pes))) if peer_pes else None,
            'pb_range': (float(min(peer_pbs)), float(max(peer_pbs))) if peer_pbs else None,
            'ev_range': (float(min(peer_evs)), float(max(peer_evs))) if peer_evs else None,
            'peer_count': len(peers),
            'data_quality': len(peer_pes) / len(peers) if peers else 0.0,
            'source': 'live_peers',
        }
        
        # Cache for 24 hours (note: default_cache.set() doesn't support expiry parameter)
        # The cache will use the default expiry from the cache instance
        default_cache.set(cache_key, result)
        
        logger.info(f"Fetched {len(peer_pes)} P/E, {len(peer_pbs)} P/B, {len(peer_evs)} EV/EBITDA from peers")
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to fetch peer multiples for {sector}: {e}")
        return _empty_peer_stats()


def _empty_peer_stats() -> dict[str, Any]:
    """Return empty peer statistics."""
    return {
        'median_pe': None,
        'median_pb': None,
        'median_ev_ebitda': None,
        'pe_range': None,
        'pb_range': None,
        'ev_range': None,
        'peer_count': 0,
        'data_quality': 0.0,
        'source': 'none',
    }


def calculate_forward_peg(
    forward_pe: float | None,
    trailing_eps: float | None,
    forward_eps: float | None,
) -> tuple[float | None, str]:
    """
    Calculate Forward PEG ratio (Peter Lynch metric).
    
    PEG = Forward P/E / (EPS Growth Rate %)
    
    Args:
        forward_pe: Forward P/E ratio
        trailing_eps: Trailing 12-month EPS
        forward_eps: Forward EPS estimate
        
    Returns:
        (peg_ratio, explanation_message)
    """
    # Validate inputs
    if not forward_pe or forward_pe <= 0:
        return None, "No forward P/E available"
    
    if not trailing_eps or not forward_eps:
        return None, "No EPS data for growth calculation"
    
    if trailing_eps <= 0:
        return None, "Trailing EPS negative (PEG undefined)"
    
    # Calculate EPS growth rate
    eps_growth = (forward_eps - trailing_eps) / trailing_eps
    
    # Handle edge cases
    if eps_growth <= 0:
        return None, f"Negative growth ({eps_growth*100:.1f}%, PEG undefined)"
    
    if eps_growth > 2.0:  # 200%+ growth (likely data error or abnormal)
        return None, f"Extreme growth ({eps_growth*100:.0f}%, PEG unreliable)"
    
    # Calculate PEG
    peg = forward_pe / (eps_growth * 100)
    
    return peg, f"Forward PEG based on {eps_growth*100:.1f}% EPS growth"


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
    peg_ratio: float | None = None
    
    # Sector benchmarks (static or live peer-based)
    sector_median_pe: float | None = None
    sector_median_pb: float | None = None
    sector_median_ev_ebitda: float | None = None
    
    # Peer statistics (if using live peers)
    peer_count: int | None = None
    peer_pe_range: tuple[float, float] | None = None  # (min, max)
    peer_pb_range: tuple[float, float] | None = None
    peer_ev_range: tuple[float, float] | None = None
    
    # Premium/discount vs sector
    pe_premium: float | None = None  # % premium/discount
    pb_premium: float | None = None
    ev_ebitda_premium: float | None = None
    
    # Classification signals
    pe_signal: str = "N/A"
    pb_signal: str = "N/A"
    ev_ebitda_signal: str = "N/A"
    peg_signal: str = "N/A"
    
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
                "peg_ratio": round(self.peg_ratio, 2) if self.peg_ratio else None,
            },
            "sector_benchmarks": {
                "median_pe": round(self.sector_median_pe, 2) if self.sector_median_pe else None,
                "median_pb": round(self.sector_median_pb, 2) if self.sector_median_pb else None,
                "median_ev_ebitda": round(self.sector_median_ev_ebitda, 2) if self.sector_median_ev_ebitda else None,
                "peer_count": self.peer_count,
            },
            "peer_ranges": {
                "pe_range": [round(self.peer_pe_range[0], 2), round(self.peer_pe_range[1], 2)] if self.peer_pe_range else None,
                "pb_range": [round(self.peer_pb_range[0], 2), round(self.peer_pb_range[1], 2)] if self.peer_pb_range else None,
                "ev_range": [round(self.peer_ev_range[0], 2), round(self.peer_ev_range[1], 2)] if self.peer_ev_range else None,
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
                "peg_signal": self.peg_signal,
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
        peg_ratio: float | None = None,
        use_live_peers: bool = True,
    ) -> RelativeMetrics:
        """
        Analyze relative valuation metrics with sector comparison.
        
        Args:
            forward_pe: Forward P/E ratio
            trailing_pe: Trailing P/E ratio
            pb_ratio: Price-to-Book ratio
            ev_ebitda: EV/EBITDA multiple
            peg_ratio: Forward PEG ratio (optional, will use forward_pe if None)
            use_live_peers: Use live peer multiples vs static benchmarks
            
        Returns:
            RelativeMetrics with signals and scores
        """
        # Get benchmarks (live peers or static)
        if use_live_peers and self.sector:
            peer_stats = get_live_peer_multiples(self.sector, exclude_ticker=self.ticker)
            sector_median_pe = peer_stats.get('median_pe') or self._get_sector_benchmark(SECTOR_PE_BENCHMARKS, DEFAULT_PE)
            sector_median_pb = peer_stats.get('median_pb') or self._get_sector_benchmark(SECTOR_PB_BENCHMARKS, DEFAULT_PB)
            sector_median_ev_ebitda = peer_stats.get('median_ev_ebitda') or self._get_sector_benchmark(SECTOR_EV_EBITDA_BENCHMARKS, DEFAULT_EV_EBITDA)
            
            peer_count = peer_stats.get('peer_count', 0)
            peer_pe_range = peer_stats.get('pe_range')
            peer_pb_range = peer_stats.get('pb_range')
            peer_ev_range = peer_stats.get('ev_range')
        else:
            # Use static benchmarks
            sector_median_pe = self._get_sector_benchmark(SECTOR_PE_BENCHMARKS, DEFAULT_PE)
            sector_median_pb = self._get_sector_benchmark(SECTOR_PB_BENCHMARKS, DEFAULT_PB)
            sector_median_ev_ebitda = self._get_sector_benchmark(SECTOR_EV_EBITDA_BENCHMARKS, DEFAULT_EV_EBITDA)
            
            peer_count = None
            peer_pe_range = None
            peer_pb_range = None
            peer_ev_range = None
        
        # Calculate premiums/discounts
        pe_premium = self._calculate_premium(forward_pe, sector_median_pe)
        pb_premium = self._calculate_premium(pb_ratio, sector_median_pb)
        ev_ebitda_premium = self._calculate_premium(ev_ebitda, sector_median_ev_ebitda)
        
        # Generate signals
        pe_signal = self._classify_multiple(pe_premium, "P/E")
        pb_signal = self._classify_multiple(pb_premium, "P/B")
        ev_ebitda_signal = self._classify_multiple(ev_ebitda_premium, "EV/EBITDA")
        peg_signal = self._classify_peg(peg_ratio)
        
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
            peg_ratio=peg_ratio,
            sector_median_pe=sector_median_pe,
            sector_median_pb=sector_median_pb,
            sector_median_ev_ebitda=sector_median_ev_ebitda,
            peer_count=peer_count,
            peer_pe_range=peer_pe_range,
            peer_pb_range=peer_pb_range,
            peer_ev_range=peer_ev_range,
            pe_premium=pe_premium,
            pb_premium=pb_premium,
            ev_ebitda_premium=ev_ebitda_premium,
            pe_signal=pe_signal,
            pb_signal=pb_signal,
            ev_ebitda_signal=ev_ebitda_signal,
            peg_signal=peg_signal,
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
    
    def _classify_peg(self, peg: float | None) -> str:
        """
        Classify PEG ratio (Peter Lynch metric).
        
        PEG < 0.5: Extremely undervalued (rare)
        PEG < 1.0: Undervalued (growth not priced in)
        PEG 1.0-1.5: Fairly valued
        PEG 1.5-2.0: Moderately expensive
        PEG > 2.0: Overvalued (paying too much for growth)
        """
        if peg is None or peg <= 0:
            return "N/A"
        
        if peg < config.PEG_EXTREMELY_CHEAP:
            return "EXTREMELY CHEAP"
        elif peg < config.PEG_UNDERVALUED:
            return "UNDERVALUED"
        elif peg < config.PEG_FAIR_MAX:
            return "FAIRLY VALUED"
        elif peg < config.PEG_MODERATE_MAX:
            return "MODERATELY EXPENSIVE"
        else:
            return "OVERVALUED"
    
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
