"""
Shiller CAPE Data Integration

Fetches Cyclically Adjusted Price-to-Earnings (CAPE) ratio from Yale's
Robert Shiller dataset. Used for equity risk adjustment based on market valuation.

Data source: http://www.econ.yale.edu/~shiller/data.htm
Update frequency: Monthly (Shiller updates dataset)

Usage:
    from src.external.shiller import get_current_cape, get_equity_risk_scalar
    
    cape = get_current_cape()
    print(f"Current CAPE: {cape}")
    
    scalar = get_equity_risk_scalar()
    print(f"Risk scalar: {scalar:.2f}x")
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
import requests


# Default CAPE thresholds and scalars (can be overridden in function calls)
CAPE_THRESHOLD_LOW = 15.0  # Below this = cheap market
CAPE_THRESHOLD_HIGH = 35.0  # Above this = expensive market
CAPE_SCALAR_LOW = 1.2  # +20% return boost when cheap
CAPE_SCALAR_HIGH = 0.7  # -30% return reduction when expensive


@dataclass
class CapeData:
    """Container for CAPE ratio and market state."""
    cape_ratio: float
    market_state: str  # "CHEAP", "FAIR", "EXPENSIVE"
    percentile: Optional[float] = None
    fetched_at: Optional[datetime] = None


# Caching for Shiller CAPE data (updates monthly, so cache for 1 week)
_cape_cache: Optional[CapeData] = None
_cape_cache_timestamp: Optional[datetime] = None
_CAPE_CACHE_HOURS = 168  # 1 week


def get_shiller_data() -> Optional[pd.DataFrame]:
    """
    Fetch full Shiller dataset from Yale website.
    
    Returns:
        DataFrame with historical CAPE ratios and market data
        None if fetch fails
    """
    from io import BytesIO
    
    try:
        # Primary URL
        url = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
        
        # Download Excel file
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Parse Excel (Shiller's file has specific format)
        df = pd.read_excel(BytesIO(response.content), sheet_name="Data", skiprows=7)
        
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Look for CAPE column (might be named "CAPE", "P/E10", or "Cyclically Adjusted PE")
        cape_col = None
        for col in df.columns:
            if any(keyword in str(col).lower() for keyword in ["cape", "p/e10", "cyclically"]):
                cape_col = col
                break
        
        if cape_col is None:
            print("⚠️  Could not find CAPE column in Shiller data")
            return None
        
        # Filter to valid CAPE values
        df = df[pd.to_numeric(df[cape_col], errors='coerce').notna()].copy()
        df['CAPE'] = pd.to_numeric(df[cape_col])
        
        return df
        
    except Exception as e:
        print(f"⚠️  Failed to fetch Shiller data: {e}")
        # Try backup URL
        from io import BytesIO
        try:
            backup_url = "https://shillerdata.com/ie_data.xls"
            response = requests.get(backup_url, timeout=30)
            response.raise_for_status()
            df = pd.read_excel(BytesIO(response.content), sheet_name="Data", skiprows=7)
            df.columns = df.columns.str.strip()
            
            # Find CAPE column
            cape_col = None
            for col in df.columns:
                if any(keyword in str(col).lower() for keyword in ["cape", "p/e10", "cyclically"]):
                    cape_col = col
                    break
            
            if cape_col:
                df = df[pd.to_numeric(df[cape_col], errors='coerce').notna()].copy()
                df['CAPE'] = pd.to_numeric(df[cape_col])
                return df
        except Exception:
            pass
        
        return None


def get_current_cape() -> float:
    """
    Fetch current CAPE ratio from Shiller dataset.
    
    Returns:
        Current CAPE ratio (e.g., 32.5)
        Fallback to 36.0 if data unavailable
    """
    global _cape_cache, _cape_cache_timestamp
    
    # Check cache
    if _cape_cache is not None and _cape_cache_timestamp is not None:
        elapsed_hours = (datetime.now() - _cape_cache_timestamp).total_seconds() / 3600
        if elapsed_hours < _CAPE_CACHE_HOURS:
            return _cape_cache.cape_ratio
    
    # Fetch new data
    df = get_shiller_data()
    
    if df is None or df.empty:
        print(f"⚠️  Using fallback CAPE value: 36.0 (December 2024 approximate)")
        return 36.0
    
    try:
        # Get most recent CAPE value
        current_cape = float(df['CAPE'].iloc[-1])
        
        # Determine market state
        if current_cape < CAPE_THRESHOLD_LOW:
            market_state = "CHEAP"
        elif current_cape > CAPE_THRESHOLD_HIGH:
            market_state = "EXPENSIVE"
        else:
            market_state = "FAIR"
        
        # Calculate historical percentile
        percentile = (df['CAPE'] < current_cape).sum() / len(df) * 100
        
        # Cache the result
        _cape_cache = CapeData(
            cape_ratio=current_cape,
            market_state=market_state,
            percentile=percentile,
            fetched_at=datetime.now()
        )
        _cape_cache_timestamp = datetime.now()
        
        return current_cape
        
    except Exception as e:
        print(f"⚠️  Error parsing CAPE data: {e}")
        print(f"   Using fallback CAPE value: 36.0")
        return 36.0


def get_equity_risk_scalar(
    cape_low: float = CAPE_THRESHOLD_LOW,
    cape_high: float = CAPE_THRESHOLD_HIGH,
    scalar_low: float = CAPE_SCALAR_LOW,
    scalar_high: float = CAPE_SCALAR_HIGH
) -> dict:
    """
    Calculate equity risk adjustment based on current CAPE ratio.
    
    Logic:
    - CAPE < 15 (cheap): Boost expected returns (+20% → 1.2x scalar)
    - CAPE 15-35 (fair): Linear interpolation between 1.2x and 0.7x
    - CAPE > 35 (expensive): Reduce expected returns (-30% → 0.7x scalar)
    
    Args:
        cape_low: CAPE threshold for cheap market (default: 15)
        cape_high: CAPE threshold for expensive market (default: 35)
        scalar_low: Return multiplier for cheap market (default: 1.2)
        scalar_high: Return multiplier for expensive market (default: 0.7)
    
    Returns:
        Dict with:
        - risk_scalar: Multiplier for expected returns
        - current_cape: Current CAPE ratio
        - regime: "CHEAP", "FAIR", or "EXPENSIVE"
        - percentile: Historical percentile of current CAPE
    """
    current_cape = get_current_cape()
    
    # Determine market state
    if current_cape < cape_low:
        market_state = "CHEAP"
        risk_scalar = scalar_low
    elif current_cape > cape_high:
        market_state = "EXPENSIVE"
        risk_scalar = scalar_high
    else:
        # Linear interpolation between thresholds
        market_state = "FAIR"
        # Map CAPE range [cape_low, cape_high] to scalar range [scalar_low, scalar_high]
        normalized_cape = (current_cape - cape_low) / (cape_high - cape_low)
        risk_scalar = scalar_low + normalized_cape * (scalar_high - scalar_low)
    
    # Get cached percentile if available
    percentile = None
    if _cape_cache is not None:
        percentile = _cape_cache.percentile
    
    return {
        "risk_scalar": risk_scalar,
        "current_cape": current_cape,
        "regime": market_state,
        "percentile": percentile,
        "thresholds": {
            "low": cape_low,
            "high": cape_high
        },
        "scalars": {
            "cheap": scalar_low,
            "expensive": scalar_high
        }
    }


def display_cape_summary(cape_data: dict) -> None:
    """
    Display formatted CAPE summary.
    
    Args:
        cape_data: Dict from get_equity_risk_scalar()
    """
    print(f"   Current CAPE: {cape_data['current_cape']:.2f} ({cape_data['regime']})")
    print(f"   Risk Scalar: {cape_data['risk_scalar']:.2f}x", end="")
    
    # Show adjustment percentage
    adjustment_pct = (cape_data['risk_scalar'] - 1.0) * 100
    if adjustment_pct > 0:
        print(f" (+{adjustment_pct:.0f}% expected returns)")
    elif adjustment_pct < 0:
        print(f" ({adjustment_pct:.0f}% expected returns)")
    else:
        print(" (no adjustment)")
    
    if cape_data.get('percentile'):
        print(f"   Historical Percentile: {cape_data['percentile']:.1f}%")
