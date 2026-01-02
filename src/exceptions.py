"""Custom exceptions for DCF Valuation Toolkit.

Provides a structured exception hierarchy for clear error handling:
- DCFError: Base exception for all DCF toolkit errors
- ValidationError: Input validation failures
- DataFetchError: External data source failures
- CalculationError: DCF calculation failures
- ConfigurationError: Configuration issues
"""

from __future__ import annotations


class DCFError(Exception):
    """Base exception for all DCF toolkit errors.
    
    All custom exceptions inherit from this, allowing:
        try:
            engine.get_intrinsic_value()
        except DCFError as e:
            handle_any_dcf_error(e)
    """
    
    def __init__(self, message: str, ticker: str | None = None, details: dict | None = None):
        self.message = message
        self.ticker = ticker
        self.details = details or {}
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        if self.ticker:
            return f"[{self.ticker}] {self.message}"
        return self.message
    
    def to_dict(self) -> dict:
        """Convert exception to dictionary for logging/API responses."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "ticker": self.ticker,
            "details": self.details,
        }


class ValidationError(DCFError):
    """Input validation failure.
    
    Raised when:
    - Invalid ticker symbol
    - Invalid parameter ranges (negative growth, WACC > 100%, etc.)
    - Missing required parameters
    - Invalid data types
    
    Example:
        raise ValidationError(
            "Growth rate must be between -50% and 100%",
            ticker="AAPL",
            details={"growth": 2.5, "min": -0.5, "max": 1.0}
        )
    """
    pass


class DataFetchError(DCFError):
    """External data source failure.
    
    Raised when:
    - yfinance API fails
    - FRED API unavailable
    - Shiller CAPE data unavailable
    - Damodaran data unavailable
    - Network timeout
    - Invalid API response
    
    Example:
        raise DataFetchError(
            "Failed to fetch stock data",
            ticker="XYZ",
            details={"source": "yfinance", "reason": "Invalid ticker"}
        )
    """
    
    def __init__(self, message: str, ticker: str | None = None, 
                 source: str | None = None, details: dict | None = None):
        self.source = source
        details = details or {}
        details["source"] = source
        super().__init__(message, ticker, details)


class CalculationError(DCFError):
    """DCF calculation failure.
    
    Raised when:
    - Negative FCF (DCF not applicable)
    - WACC <= terminal growth (infinite value)
    - Division by zero
    - Numerical overflow
    - Impossible scenarios
    
    Example:
        raise CalculationError(
            "Cannot calculate terminal value: WACC <= terminal growth",
            ticker="AAPL",
            details={"wacc": 0.02, "terminal_growth": 0.025}
        )
    """
    pass


class ConfigurationError(DCFError):
    """Configuration issue.
    
    Raised when:
    - Missing required config values
    - Invalid config values
    - Missing API keys
    - Invalid environment setup
    
    Example:
        raise ConfigurationError(
            "FRED_API_KEY not found in environment",
            details={"required_env_var": "FRED_API_KEY"}
        )
    """
    pass


class InsufficientDataError(DataFetchError):
    """Insufficient data for analysis.
    
    Raised when:
    - No FCF data available
    - No revenue data for EV/Sales
    - No price history for volatility
    - Missing required financial metrics
    
    Example:
        raise InsufficientDataError(
            "No free cash flow data available",
            ticker="RIVN",
            details={"required": "FCF", "available": ["revenue", "market_cap"]}
        )
    """
    pass


class RateLimitError(DataFetchError):
    """API rate limit exceeded.
    
    Raised when:
    - yfinance rate limit hit
    - FRED API quota exceeded
    - Too many requests in short period
    
    Example:
        raise RateLimitError(
            "Rate limit exceeded, retry after 60 seconds",
            source="yfinance",
            details={"retry_after": 60}
        )
    """
    
    def __init__(self, message: str, source: str | None = None, 
                 retry_after: int | None = None, details: dict | None = None):
        self.retry_after = retry_after
        details = details or {}
        details["retry_after"] = retry_after
        super().__init__(message, source=source, details=details)
