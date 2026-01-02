"""yfinance data validation and sanitization layer.

Provides robust validation for yfinance API responses with:
- Null/missing field detection
- Type coercion and normalization
- Outlier detection and capping
- Fallback value generation

Usage:
    from src.data_validator import validate_yfinance_info, validate_cashflow_data
    
    info = yf.Ticker("AAPL").info
    validated = validate_yfinance_info(info, ticker="AAPL")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.exceptions import DataFetchError, InsufficientDataError, ValidationError
from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ValidatedCompanyInfo:
    """Validated and normalized company info from yfinance."""
    ticker: str
    current_price: float
    shares_outstanding: float  # millions
    market_cap: float  # billions
    beta: float
    analyst_growth: float | None
    revenue: float | None  # millions
    sector: str | None
    industry: str | None
    
    # Validation metadata
    warnings: list[str]
    data_quality_score: float  # 0.0 to 1.0


@dataclass
class ValidatedCashflowData:
    """Validated cashflow data from yfinance."""
    ticker: str
    fcf_quarterly: float  # Most recent quarter (millions)
    fcf_annual: float  # Annualized (millions)
    fcf_trend: str  # "improving", "declining", "stable"
    quarters_available: int
    
    # Validation metadata
    warnings: list[str]


# =============================================================================
# Info Validation
# =============================================================================

def validate_yfinance_info(info: dict | None, ticker: str) -> ValidatedCompanyInfo:
    """Validate and normalize yfinance stock info.
    
    Args:
        info: Raw info dict from yf.Ticker().info
        ticker: Stock ticker symbol
        
    Returns:
        ValidatedCompanyInfo with sanitized data
        
    Raises:
        DataFetchError: If info is None or empty
        InsufficientDataError: If critical fields are missing
    """
    warnings: list[str] = []
    data_quality_score = 1.0
    
    # Check for null/empty response
    if not info:
        raise DataFetchError(
            "Empty response from yfinance",
            ticker=ticker,
            source="yfinance",
            details={"reason": "info dict is None or empty"}
        )
    
    # Validate current price (critical)
    current_price = _extract_price(info, ticker)
    if current_price <= 0:
        raise InsufficientDataError(
            "No valid price data available",
            ticker=ticker,
            source="yfinance",
            details={"fields_checked": ["currentPrice", "regularMarketPrice", "previousClose"]}
        )
    
    # Validate shares outstanding (critical)
    shares = _extract_shares(info, ticker)
    if shares <= 0:
        raise InsufficientDataError(
            "No valid shares outstanding data",
            ticker=ticker,
            source="yfinance",
            details={"shares_raw": info.get("sharesOutstanding")}
        )
    shares_millions = shares / 1e6
    
    # Market cap (can calculate if missing)
    market_cap = info.get("marketCap", 0)
    if market_cap <= 0:
        market_cap = current_price * shares
        warnings.append("Market cap calculated from price × shares")
    market_cap_billions = market_cap / 1e9
    
    # Beta (with fallback)
    beta = _extract_beta(info, ticker, warnings)
    
    # Analyst growth (with validation)
    analyst_growth = _extract_analyst_growth(info, ticker, warnings)
    
    # Revenue
    revenue = info.get("totalRevenue")
    if revenue:
        revenue = revenue / 1e6
        if revenue < 0:
            warnings.append(f"Negative revenue reported: ${revenue:.1f}M")
            data_quality_score -= 0.1
    else:
        warnings.append("No revenue data available")
        data_quality_score -= 0.05
    
    # Sector and industry
    sector = info.get("sector")
    industry = info.get("industry")
    if not sector:
        warnings.append("No sector classification")
        data_quality_score -= 0.05
    
    # Log validation result
    if warnings:
        logger.warning(
            f"Data validation warnings for {ticker}",
            ticker=ticker,
            warnings=warnings,
            quality_score=round(data_quality_score, 2)
        )
    
    return ValidatedCompanyInfo(
        ticker=ticker,
        current_price=current_price,
        shares_outstanding=shares_millions,
        market_cap=market_cap_billions,
        beta=beta,
        analyst_growth=analyst_growth,
        revenue=revenue,
        sector=sector,
        industry=industry,
        warnings=warnings,
        data_quality_score=max(0.0, data_quality_score),
    )


def _extract_price(info: dict, ticker: str) -> float:
    """Extract current price from multiple possible fields."""
    price_fields = ["currentPrice", "regularMarketPrice", "previousClose", "open"]
    
    for field in price_fields:
        price = info.get(field)
        if price and isinstance(price, (int, float)) and price > 0:
            return float(price)
    
    return 0.0


def _extract_shares(info: dict, ticker: str) -> float:
    """Extract shares outstanding with fallbacks."""
    shares = info.get("sharesOutstanding", 0)
    
    if not shares or shares <= 0:
        # Try float shares
        shares = info.get("floatShares", 0)
    
    if not shares or shares <= 0:
        # Try implied shares (market cap / price)
        market_cap = info.get("marketCap", 0)
        price = _extract_price(info, ticker)
        if market_cap > 0 and price > 0:
            shares = market_cap / price
    
    return float(shares) if shares else 0.0


def _extract_beta(info: dict, ticker: str, warnings: list[str]) -> float:
    """Extract and validate beta with sector fallback."""
    beta = info.get("beta")
    
    if beta is None:
        warnings.append("No beta available, using 1.0")
        return 1.0
    
    if not isinstance(beta, (int, float)):
        warnings.append(f"Invalid beta type: {type(beta)}, using 1.0")
        return 1.0
    
    # Sanity check: beta should be 0 < beta < 5
    if beta <= 0:
        warnings.append(f"Non-positive beta ({beta}), using 1.0")
        return 1.0
    
    if beta > 5.0:
        warnings.append(f"Extreme beta ({beta:.2f}), capping at 5.0")
        return 5.0
    
    return float(beta)


def _extract_analyst_growth(info: dict, ticker: str, warnings: list[str]) -> float | None:
    """Extract and validate analyst growth estimate."""
    # Try multiple growth fields
    growth_fields = ["earningsGrowth", "revenueGrowth", "earningsQuarterlyGrowth"]
    
    for field in growth_fields:
        growth = info.get(field)
        if growth is not None and isinstance(growth, (int, float)):
            # yfinance sometimes returns as percentage (25.0) instead of decimal (0.25)
            if abs(growth) > 1:
                growth = growth / 100
            
            # Cap extreme values
            if growth > 1.0:
                warnings.append(f"Extreme growth estimate ({growth*100:.1f}%), capping at 100%")
                return 1.0
            if growth < -0.5:
                warnings.append(f"Extreme negative growth ({growth*100:.1f}%), capping at -50%")
                return -0.5
            
            return float(growth)
    
    warnings.append("No analyst growth estimate available")
    return None


# =============================================================================
# Cashflow Validation
# =============================================================================

def validate_cashflow_data(cashflow: pd.DataFrame | None, ticker: str) -> ValidatedCashflowData:
    """Validate and process yfinance cashflow data.
    
    Args:
        cashflow: Raw cashflow DataFrame from yf.Ticker().quarterly_cashflow
        ticker: Stock ticker symbol
        
    Returns:
        ValidatedCashflowData with processed FCF data
        
    Raises:
        InsufficientDataError: If no valid FCF data available
    """
    warnings: list[str] = []
    
    # Check for null/empty DataFrame
    if cashflow is None or cashflow.empty:
        raise InsufficientDataError(
            "No cashflow data available",
            ticker=ticker,
            source="yfinance",
            details={"reason": "cashflow DataFrame is None or empty"}
        )
    
    # Check for Free Cash Flow row
    if "Free Cash Flow" not in cashflow.index:
        # Try alternative names
        fcf_names = ["Free Cash Flow", "FreeCashFlow", "freeCashFlow"]
        found = False
        for name in fcf_names:
            if name in cashflow.index:
                cashflow = cashflow.rename(index={name: "Free Cash Flow"})
                found = True
                break
        
        if not found:
            raise InsufficientDataError(
                "No Free Cash Flow data in cashflow statement",
                ticker=ticker,
                source="yfinance",
                details={"available_rows": list(cashflow.index)[:10]}
            )
    
    # Extract FCF values
    fcf_series = cashflow.loc["Free Cash Flow"].dropna()
    
    if len(fcf_series) == 0:
        raise InsufficientDataError(
            "All FCF values are NaN",
            ticker=ticker,
            source="yfinance"
        )
    
    # Most recent quarterly FCF (in millions)
    fcf_quarterly = float(fcf_series.iloc[0]) / 1e6
    
    # Annualized FCF
    quarters_available = len(fcf_series)
    if quarters_available >= 4:
        # Sum last 4 quarters
        fcf_annual = float(fcf_series.iloc[:4].sum()) / 1e6
    else:
        # Extrapolate
        fcf_annual = fcf_quarterly * 4
        warnings.append(f"Only {quarters_available} quarters available, annualized from Q1")
    
    # Determine trend
    if quarters_available >= 2:
        current = float(fcf_series.iloc[0])
        previous = float(fcf_series.iloc[1])
        if current > previous * 1.1:
            fcf_trend = "improving"
        elif current < previous * 0.9:
            fcf_trend = "declining"
        else:
            fcf_trend = "stable"
    else:
        fcf_trend = "unknown"
        warnings.append("Insufficient history for trend analysis")
    
    # Log validation
    if warnings:
        logger.warning(
            f"Cashflow validation warnings for {ticker}",
            ticker=ticker,
            warnings=warnings
        )
    
    return ValidatedCashflowData(
        ticker=ticker,
        fcf_quarterly=fcf_quarterly,
        fcf_annual=fcf_annual,
        fcf_trend=fcf_trend,
        quarters_available=quarters_available,
        warnings=warnings,
    )


# =============================================================================
# Composite Validation
# =============================================================================

def validate_company_data(
    info: dict | None,
    cashflow: pd.DataFrame | None,
    ticker: str
) -> tuple[ValidatedCompanyInfo, ValidatedCashflowData | None]:
    """Validate both info and cashflow data.
    
    Args:
        info: Raw info dict from yfinance
        cashflow: Raw cashflow DataFrame from yfinance
        ticker: Stock ticker symbol
        
    Returns:
        (ValidatedCompanyInfo, ValidatedCashflowData or None)
        
    Raises:
        DataFetchError: If critical data is missing
    """
    # Validate info (required)
    validated_info = validate_yfinance_info(info, ticker)
    
    # Validate cashflow (optional - may use EV/Sales for negative FCF companies)
    try:
        validated_cashflow = validate_cashflow_data(cashflow, ticker)
    except InsufficientDataError as e:
        logger.info(
            f"No FCF data for {ticker}, may use EV/Sales valuation",
            ticker=ticker,
            error=str(e)
        )
        validated_cashflow = None
    
    return validated_info, validated_cashflow


def calculate_data_quality_score(
    info: ValidatedCompanyInfo,
    cashflow: ValidatedCashflowData | None
) -> float:
    """Calculate overall data quality score.
    
    Returns:
        Score from 0.0 (poor) to 1.0 (excellent)
    """
    score = info.data_quality_score
    
    # Penalize missing cashflow
    if cashflow is None:
        score -= 0.2
    elif cashflow.fcf_annual < 0:
        score -= 0.1  # Negative FCF limits analysis options
    
    # Bonus for complete data
    if info.sector and info.industry:
        score += 0.05
    
    return max(0.0, min(1.0, score))
