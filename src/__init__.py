"""DCF Valuation Toolkit - Core modules."""

# Load environment variables first (must be before other imports)
from . import env_loader  # noqa: F401

from .config import config
from .dcf_engine import CompanyData, DCFEngine
from .exceptions import (
    DCFError,
    ValidationError,
    DataFetchError,
    CalculationError,
    ConfigurationError,
    InsufficientDataError,
    RateLimitError,
)
from .logging_config import get_logger, log_performance, Timer
from .optimizer import OptimizationMethod, PortfolioEngine
from .portfolio import optimize_portfolio_with_dcf
from .regime import MarketRegime, RegimeDetector
from .validation import (
    DCFParams,
    TickerInput,
    validate_dcf_params,
    validate_ticker,
    validate_tickers,
)

__all__ = [
    # Config
    "config",
    # Engine
    "DCFEngine",
    "CompanyData",
    # Portfolio
    "optimize_portfolio_with_dcf",
    "PortfolioEngine",
    "OptimizationMethod",
    # Regime
    "RegimeDetector",
    "MarketRegime",
    # Exceptions
    "DCFError",
    "ValidationError",
    "DataFetchError",
    "CalculationError",
    "ConfigurationError",
    "InsufficientDataError",
    "RateLimitError",
    # Logging
    "get_logger",
    "log_performance",
    "Timer",
    # Validation
    "DCFParams",
    "TickerInput",
    "validate_dcf_params",
    "validate_ticker",
    "validate_tickers",
]
