"""Pydantic validation models for DCF Valuation Toolkit.

Provides type-safe input validation for:
- DCF calculation parameters
- Portfolio optimization inputs
- API responses from external data sources

All models use Pydantic v2 syntax with field validators.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from src.config import config


# =============================================================================
# DCF Input Validation
# =============================================================================

class DCFParams(BaseModel):
    """Validated DCF calculation parameters.
    
    Example:
        params = DCFParams(
            growth=0.15,
            terminal_growth=0.025,
            wacc=0.10,
            years=5
        )
    """
    growth: Annotated[float, Field(ge=-0.50, le=1.0, description="Annual growth rate (-50% to 100%)")]
    terminal_growth: Annotated[float, Field(ge=0.0, le=0.05, description="Terminal growth rate (0% to 5%)")] = 0.025
    wacc: Annotated[float, Field(gt=0.0, le=0.50, description="WACC (0% to 50%)")] = 0.10
    years: Annotated[int, Field(ge=1, le=20, description="Forecast years (1 to 20)")] = 5
    terminal_method: Literal["gordon_growth", "exit_multiple"] = "gordon_growth"
    exit_multiple: Annotated[float | None, Field(ge=1.0, le=100.0, description="Exit multiple (1x to 100x)")] = None
    
    @model_validator(mode='after')
    def validate_wacc_vs_terminal(self) -> "DCFParams":
        """Ensure WACC > terminal growth for Gordon Growth method."""
        if self.terminal_method == "gordon_growth" and self.wacc <= self.terminal_growth:
            raise ValueError(
                f"WACC ({self.wacc:.1%}) must be greater than terminal growth ({self.terminal_growth:.1%}) "
                "for Gordon Growth method. Consider using exit_multiple method instead."
            )
        return self


class TickerInput(BaseModel):
    """Validated stock ticker input.
    
    Example:
        ticker = TickerInput(symbol="AAPL")
        print(ticker.symbol)  # "AAPL"
    """
    symbol: Annotated[str, Field(min_length=1, max_length=10, description="Stock ticker symbol")]
    
    @field_validator('symbol')
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        """Normalize ticker to uppercase, stripped."""
        normalized = v.upper().strip()
        if not normalized.isalnum() and '.' not in normalized and '-' not in normalized:
            raise ValueError(f"Invalid ticker symbol: {v}")
        return normalized


class MultiTickerInput(BaseModel):
    """Validated list of stock tickers.
    
    Example:
        tickers = MultiTickerInput(symbols=["AAPL", "MSFT", "GOOGL"])
    """
    symbols: Annotated[list[str], Field(min_length=1, max_length=50, description="List of ticker symbols")]
    
    @field_validator('symbols')
    @classmethod
    def normalize_tickers(cls, v: list[str]) -> list[str]:
        """Normalize all tickers and remove duplicates."""
        normalized = []
        seen = set()
        for ticker in v:
            t = ticker.upper().strip()
            if t and t not in seen:
                normalized.append(t)
                seen.add(t)
        if not normalized:
            raise ValueError("At least one valid ticker required")
        return normalized


# =============================================================================
# Company Data Validation
# =============================================================================

class CompanyDataInput(BaseModel):
    """Validated company financial data from yfinance.
    
    Used to validate raw API responses before processing.
    """
    ticker: str
    fcf: Annotated[float, Field(description="Free Cash Flow (millions, annualized)")]
    shares: Annotated[float, Field(gt=0, description="Shares outstanding (millions)")]
    current_price: Annotated[float, Field(gt=0, description="Current stock price")]
    market_cap: Annotated[float, Field(ge=0, description="Market cap (billions)")]
    beta: Annotated[float, Field(ge=0, le=5.0, description="Beta coefficient (0 to 5)")] = 1.0
    analyst_growth: Annotated[float | None, Field(ge=-1.0, le=2.0, description="Analyst growth estimate")] = None
    revenue: Annotated[float | None, Field(ge=0, description="Total revenue (millions)")] = None
    sector: str | None = None
    
    @field_validator('beta')
    @classmethod
    def validate_beta(cls, v: float) -> float:
        """Ensure beta is reasonable, default to 1.0 if not."""
        if v <= 0 or v > 5.0:
            return 1.0
        return v
    
    @field_validator('analyst_growth')
    @classmethod
    def cap_growth(cls, v: float | None) -> float | None:
        """Cap extreme growth estimates."""
        if v is None:
            return None
        # Cap at +/- 100%
        return max(-1.0, min(1.0, v))


# =============================================================================
# Portfolio Optimization Validation
# =============================================================================

class PortfolioParams(BaseModel):
    """Validated portfolio optimization parameters.
    
    Example:
        params = PortfolioParams(
            tickers=["AAPL", "MSFT", "GOOGL"],
            method="max_sharpe",
            risk_free_rate=0.04
        )
    """
    tickers: Annotated[list[str], Field(min_length=2, max_length=50, description="Portfolio tickers")]
    method: Literal["max_sharpe", "min_volatility", "equal_weight", "risk_parity"] = "max_sharpe"
    risk_free_rate: Annotated[float, Field(ge=0.0, le=0.20, description="Risk-free rate (0% to 20%)")] = config.RISK_FREE_RATE
    target_return: Annotated[float | None, Field(ge=0.0, le=1.0, description="Target annual return")] = None
    max_weight: Annotated[float, Field(gt=0.0, le=1.0, description="Maximum weight per asset")] = 0.40
    min_weight: Annotated[float, Field(ge=0.0, lt=1.0, description="Minimum weight per asset")] = 0.0
    
    @field_validator('tickers')
    @classmethod
    def normalize_tickers(cls, v: list[str]) -> list[str]:
        """Normalize tickers."""
        return [t.upper().strip() for t in v if t.strip()]
    
    @model_validator(mode='after')
    def validate_weights(self) -> "PortfolioParams":
        """Ensure weight constraints are valid."""
        if self.min_weight >= self.max_weight:
            raise ValueError(
                f"min_weight ({self.min_weight}) must be less than max_weight ({self.max_weight})"
            )
        return self


# =============================================================================
# External Data Validation
# =============================================================================

class FREDMacroData(BaseModel):
    """Validated FRED macro data response."""
    risk_free_rate: Annotated[float, Field(ge=0.0, le=0.20, description="10Y Treasury rate")]
    inflation_rate: Annotated[float | None, Field(ge=-0.10, le=0.30, description="CPI YoY")] = None
    gdp_growth: Annotated[float | None, Field(ge=-0.20, le=0.30, description="Real GDP growth")] = None
    fetched_at: str | None = None
    source: str = "FRED"


class ShillerCAPEData(BaseModel):
    """Validated Shiller CAPE data response."""
    cape_ratio: Annotated[float, Field(gt=0, le=100, description="CAPE ratio")]
    market_state: Literal["CHEAP", "FAIR", "EXPENSIVE"]
    percentile: Annotated[float | None, Field(ge=0, le=100, description="Historical percentile")] = None
    risk_scalar: Annotated[float, Field(gt=0, le=2.0, description="Risk adjustment scalar")] = 1.0


class DamodaranPriors(BaseModel):
    """Validated Damodaran sector priors."""
    sector: str
    beta: Annotated[float | None, Field(ge=0, le=5.0, description="Sector beta")] = None
    unlevered_beta: Annotated[float | None, Field(ge=0, le=5.0, description="Unlevered beta")] = None
    operating_margin: Annotated[float | None, Field(ge=-1.0, le=1.0, description="Operating margin")] = None
    revenue_growth: Annotated[float | None, Field(ge=-0.5, le=1.0, description="Revenue growth")] = None


# =============================================================================
# Utility Functions
# =============================================================================

def validate_dcf_params(
    growth: float | None = None,
    terminal_growth: float = 0.025,
    wacc: float | None = None,
    years: int = 5,
    terminal_method: str = "gordon_growth",
    exit_multiple: float | None = None,
    default_growth: float = 0.08,
    default_wacc: float = 0.10,
) -> DCFParams:
    """Validate and create DCFParams with defaults.
    
    Args:
        growth: Growth rate (uses default if None)
        terminal_growth: Terminal growth rate
        wacc: WACC (uses default if None)
        years: Forecast years
        terminal_method: 'gordon_growth' or 'exit_multiple'
        exit_multiple: Exit multiple for terminal value
        default_growth: Default growth if None provided
        default_wacc: Default WACC if None provided
        
    Returns:
        Validated DCFParams object
        
    Raises:
        ValidationError: If parameters are invalid
    """
    from src.exceptions import ValidationError
    
    try:
        return DCFParams(
            growth=growth if growth is not None else default_growth,
            terminal_growth=terminal_growth,
            wacc=wacc if wacc is not None else default_wacc,
            years=years,
            terminal_method=terminal_method,
            exit_multiple=exit_multiple,
        )
    except Exception as e:
        raise ValidationError(
            f"Invalid DCF parameters: {e}",
            details={
                "growth": growth,
                "terminal_growth": terminal_growth,
                "wacc": wacc,
                "years": years,
            }
        ) from e


def validate_ticker(symbol: str) -> str:
    """Validate and normalize a ticker symbol.
    
    Args:
        symbol: Raw ticker input
        
    Returns:
        Normalized ticker (uppercase, stripped)
        
    Raises:
        ValidationError: If ticker is invalid
    """
    from src.exceptions import ValidationError
    
    try:
        validated = TickerInput(symbol=symbol)
        return validated.symbol
    except Exception as e:
        raise ValidationError(
            f"Invalid ticker symbol: {symbol}",
            details={"symbol": symbol, "error": str(e)}
        ) from e


def validate_tickers(symbols: list[str]) -> list[str]:
    """Validate and normalize multiple ticker symbols.
    
    Args:
        symbols: List of raw ticker inputs
        
    Returns:
        List of normalized tickers
        
    Raises:
        ValidationError: If any ticker is invalid
    """
    from src.exceptions import ValidationError
    
    try:
        validated = MultiTickerInput(symbols=symbols)
        return validated.symbols
    except Exception as e:
        raise ValidationError(
            f"Invalid ticker list",
            details={"symbols": symbols, "error": str(e)}
        ) from e
