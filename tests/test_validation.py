"""Tests for validation, exceptions, and data validation modules.

Tests Phase 3 additions:
- Custom exception hierarchy
- Pydantic validation models
- yfinance data validation layer
"""

import pytest
import pandas as pd
from datetime import datetime

from src.exceptions import (
    DCFError,
    ValidationError,
    DataFetchError,
    CalculationError,
    ConfigurationError,
    InsufficientDataError,
    RateLimitError,
)
from src.validation import (
    DCFParams,
    TickerInput,
    MultiTickerInput,
    CompanyDataInput,
    PortfolioParams,
    validate_dcf_params,
    validate_ticker,
    validate_tickers,
)
from src.data_validator import (
    validate_yfinance_info,
    validate_cashflow_data,
    validate_company_data,
    ValidatedCompanyInfo,
    ValidatedCashflowData,
)


# =============================================================================
# Exception Hierarchy Tests
# =============================================================================

class TestExceptionHierarchy:
    """Test custom exception classes."""

    def test_dcf_error_base(self):
        """Test base DCFError."""
        error = DCFError("Test error", ticker="AAPL", details={"key": "value"})
        assert "AAPL" in str(error)
        assert error.ticker == "AAPL"
        assert error.details == {"key": "value"}

    def test_dcf_error_to_dict(self):
        """Test exception serialization."""
        error = DCFError("Test error", ticker="MSFT", details={"foo": "bar"})
        result = error.to_dict()
        assert result["error_type"] == "DCFError"
        assert result["message"] == "Test error"
        assert result["ticker"] == "MSFT"
        assert result["details"]["foo"] == "bar"

    def test_validation_error_inheritance(self):
        """Test ValidationError inherits from DCFError."""
        error = ValidationError("Invalid input", ticker="TEST")
        assert isinstance(error, DCFError)
        assert isinstance(error, Exception)

    def test_data_fetch_error_with_source(self):
        """Test DataFetchError with source info."""
        error = DataFetchError(
            "API failed",
            ticker="XYZ",
            source="yfinance",
            details={"status": 500}
        )
        assert error.source == "yfinance"
        assert error.details["source"] == "yfinance"
        assert error.details["status"] == 500

    def test_calculation_error(self):
        """Test CalculationError for DCF failures."""
        error = CalculationError(
            "WACC <= terminal growth",
            ticker="AAPL",
            details={"wacc": 0.02, "term_growth": 0.025}
        )
        assert isinstance(error, DCFError)
        assert "AAPL" in str(error)

    def test_insufficient_data_error(self):
        """Test InsufficientDataError inheritance."""
        error = InsufficientDataError(
            "No FCF data",
            ticker="RIVN",
            source="yfinance"
        )
        assert isinstance(error, DataFetchError)
        assert isinstance(error, DCFError)

    def test_rate_limit_error(self):
        """Test RateLimitError with retry_after."""
        error = RateLimitError(
            "Too many requests",
            source="yfinance",
            retry_after=60
        )
        assert error.retry_after == 60
        assert error.details["retry_after"] == 60

    def test_exception_catching_hierarchy(self):
        """Test that child exceptions are caught by parent handlers."""
        exceptions_to_test = [
            ValidationError("test"),
            DataFetchError("test"),
            CalculationError("test"),
            ConfigurationError("test"),
            InsufficientDataError("test"),
            RateLimitError("test"),
        ]
        for exc in exceptions_to_test:
            try:
                raise exc
            except DCFError as e:
                assert True  # Should be caught
            except Exception:
                pytest.fail(f"{type(exc).__name__} not caught by DCFError handler")


# =============================================================================
# Pydantic Validation Tests
# =============================================================================

class TestDCFParamsValidation:
    """Test DCFParams Pydantic model."""

    def test_valid_params(self):
        """Test valid DCF parameters."""
        params = DCFParams(
            growth=0.15,
            terminal_growth=0.025,
            wacc=0.10,
            years=5
        )
        assert params.growth == 0.15
        assert params.wacc == 0.10
        assert params.years == 5

    def test_growth_bounds(self):
        """Test growth rate bounds validation."""
        # Valid bounds
        DCFParams(growth=-0.50, wacc=0.10)  # Min growth
        DCFParams(growth=1.0, wacc=0.10)    # Max growth

        # Invalid bounds
        with pytest.raises(ValueError):
            DCFParams(growth=-0.60, wacc=0.10)  # Too low
        with pytest.raises(ValueError):
            DCFParams(growth=1.5, wacc=0.10)    # Too high

    def test_wacc_bounds(self):
        """Test WACC bounds validation."""
        # Valid (WACC > default terminal growth of 0.025)
        DCFParams(growth=0.10, wacc=0.03)   # Low WACC but > term_growth
        DCFParams(growth=0.10, wacc=0.50)   # High WACC

        # Invalid
        with pytest.raises(ValueError):
            DCFParams(growth=0.10, wacc=0.0)    # Zero WACC
        with pytest.raises(ValueError):
            DCFParams(growth=0.10, wacc=0.60)   # Too high

    def test_wacc_vs_terminal_growth(self):
        """Test WACC must be > terminal growth for Gordon Growth."""
        with pytest.raises(ValueError) as exc_info:
            DCFParams(
                growth=0.10,
                terminal_growth=0.05,
                wacc=0.04,  # Less than terminal growth!
                terminal_method="gordon_growth"
            )
        assert "greater than terminal growth" in str(exc_info.value)

    def test_exit_multiple_method(self):
        """Test exit multiple terminal method."""
        params = DCFParams(
            growth=0.10,
            terminal_growth=0.05,
            wacc=0.04,  # Can be < terminal growth with exit multiple
            terminal_method="exit_multiple",
            exit_multiple=15.0
        )
        assert params.terminal_method == "exit_multiple"
        assert params.exit_multiple == 15.0


class TestTickerValidation:
    """Test ticker input validation."""

    def test_valid_ticker(self):
        """Test valid ticker normalization."""
        ticker = TickerInput(symbol="aapl")
        assert ticker.symbol == "AAPL"

    def test_ticker_with_spaces(self):
        """Test ticker with leading/trailing spaces."""
        ticker = TickerInput(symbol="  msft  ")
        assert ticker.symbol == "MSFT"

    def test_ticker_with_dot(self):
        """Test ticker with dot (e.g., BRK.B)."""
        ticker = TickerInput(symbol="brk.b")
        assert ticker.symbol == "BRK.B"

    def test_empty_ticker_rejected(self):
        """Test empty ticker is rejected."""
        with pytest.raises(ValueError):
            TickerInput(symbol="")

    def test_validate_ticker_function(self):
        """Test validate_ticker utility function."""
        assert validate_ticker("aapl") == "AAPL"
        assert validate_ticker("  MSFT  ") == "MSFT"

    def test_validate_tickers_function(self):
        """Test validate_tickers utility function."""
        result = validate_tickers(["aapl", "msft", "googl"])
        assert result == ["AAPL", "MSFT", "GOOGL"]

    def test_validate_tickers_removes_duplicates(self):
        """Test duplicate removal."""
        result = validate_tickers(["AAPL", "aapl", "MSFT", "msft"])
        assert result == ["AAPL", "MSFT"]


class TestMultiTickerValidation:
    """Test MultiTickerInput validation."""

    def test_valid_tickers(self):
        """Test valid ticker list."""
        tickers = MultiTickerInput(symbols=["AAPL", "MSFT", "GOOGL"])
        assert len(tickers.symbols) == 3
        assert "AAPL" in tickers.symbols

    def test_empty_list_rejected(self):
        """Test empty list is rejected."""
        with pytest.raises(ValueError):
            MultiTickerInput(symbols=[])

    def test_duplicates_removed(self):
        """Test duplicates are removed."""
        tickers = MultiTickerInput(symbols=["AAPL", "aapl", "AAPL"])
        assert tickers.symbols == ["AAPL"]


class TestPortfolioParamsValidation:
    """Test PortfolioParams validation."""

    def test_valid_portfolio_params(self):
        """Test valid portfolio parameters."""
        params = PortfolioParams(
            tickers=["AAPL", "MSFT", "GOOGL"],
            method="max_sharpe",
            risk_free_rate=0.04
        )
        assert params.method == "max_sharpe"
        assert len(params.tickers) == 3

    def test_min_tickers_required(self):
        """Test minimum 2 tickers required."""
        with pytest.raises(ValueError):
            PortfolioParams(tickers=["AAPL"])  # Only 1 ticker

    def test_weight_constraints(self):
        """Test weight constraint validation."""
        with pytest.raises(ValueError):
            PortfolioParams(
                tickers=["AAPL", "MSFT"],
                min_weight=0.5,
                max_weight=0.3  # min > max!
            )


class TestValidateDCFParamsFunction:
    """Test validate_dcf_params utility function."""

    def test_with_defaults(self):
        """Test with default values."""
        params = validate_dcf_params()
        assert params.growth == 0.08  # default_growth
        assert params.wacc == 0.10    # default_wacc

    def test_with_provided_values(self):
        """Test with provided values."""
        params = validate_dcf_params(
            growth=0.20,
            wacc=0.12,
            years=7
        )
        assert params.growth == 0.20
        assert params.wacc == 0.12
        assert params.years == 7


# =============================================================================
# Data Validator Tests
# =============================================================================

class TestYFinanceInfoValidation:
    """Test yfinance info validation."""

    def test_valid_info(self):
        """Test validation of valid info dict."""
        info = {
            "currentPrice": 150.0,
            "sharesOutstanding": 16000000000,
            "marketCap": 2400000000000,
            "beta": 1.2,
            "earningsGrowth": 0.15,
            "totalRevenue": 400000000000,
            "sector": "Technology",
            "industry": "Consumer Electronics",
        }
        result = validate_yfinance_info(info, "AAPL")
        assert isinstance(result, ValidatedCompanyInfo)
        assert result.ticker == "AAPL"
        assert result.current_price == 150.0
        assert result.beta == 1.2
        assert result.sector == "Technology"

    def test_empty_info_rejected(self):
        """Test empty info dict is rejected."""
        with pytest.raises(DataFetchError):
            validate_yfinance_info(None, "TEST")

        with pytest.raises(DataFetchError):
            validate_yfinance_info({}, "TEST")

    def test_missing_price_rejected(self):
        """Test missing price is rejected."""
        info = {
            "sharesOutstanding": 16000000000,
            "marketCap": 2400000000000,
        }
        with pytest.raises(InsufficientDataError):
            validate_yfinance_info(info, "TEST")

    def test_beta_normalization(self):
        """Test beta is normalized to valid range."""
        # Negative beta -> 1.0
        info = {
            "currentPrice": 100.0,
            "sharesOutstanding": 1000000000,
            "beta": -0.5,
        }
        result = validate_yfinance_info(info, "TEST")
        assert result.beta == 1.0
        assert any("Non-positive beta" in w for w in result.warnings)

        # Extreme beta -> capped at 5.0
        info["beta"] = 7.5
        result = validate_yfinance_info(info, "TEST")
        assert result.beta == 5.0

    def test_analyst_growth_capping(self):
        """Test analyst growth is capped to valid range."""
        info = {
            "currentPrice": 100.0,
            "sharesOutstanding": 1000000000,
            "earningsGrowth": 150.0,  # 15000% as percentage - extreme
        }
        result = validate_yfinance_info(info, "TEST")
        # 150.0 / 100 = 1.5, capped at 1.0 (100%)
        assert result.analyst_growth == 1.0  # Capped at 100%


class TestCashflowValidation:
    """Test cashflow data validation."""

    def test_valid_cashflow(self):
        """Test validation of valid cashflow DataFrame."""
        # Create mock cashflow data
        dates = pd.date_range(end=datetime.now(), periods=4, freq="QE")
        cashflow = pd.DataFrame(
            {"Q1": [1e9, 5e8], "Q2": [1.1e9, 5.5e8], "Q3": [1.2e9, 6e8], "Q4": [1.3e9, 6.5e8]},
            index=["Free Cash Flow", "Operating Cash Flow"]
        )

        result = validate_cashflow_data(cashflow, "AAPL")
        assert isinstance(result, ValidatedCashflowData)
        assert result.ticker == "AAPL"
        assert result.fcf_quarterly > 0
        assert result.quarters_available == 4

    def test_empty_cashflow_rejected(self):
        """Test empty cashflow is rejected."""
        with pytest.raises(InsufficientDataError):
            validate_cashflow_data(None, "TEST")

        with pytest.raises(InsufficientDataError):
            validate_cashflow_data(pd.DataFrame(), "TEST")

    def test_missing_fcf_rejected(self):
        """Test missing FCF row is rejected."""
        cashflow = pd.DataFrame(
            {"Q1": [5e8], "Q2": [5.5e8]},
            index=["Operating Cash Flow"]  # No "Free Cash Flow"
        )
        with pytest.raises(InsufficientDataError):
            validate_cashflow_data(cashflow, "TEST")

    def test_fcf_trend_detection(self):
        """Test FCF trend detection."""
        # Improving trend
        cashflow = pd.DataFrame(
            {"Q1": [1.5e9], "Q2": [1.0e9]},  # Q1 > Q2 by >10%
            index=["Free Cash Flow"]
        )
        result = validate_cashflow_data(cashflow, "TEST")
        assert result.fcf_trend == "improving"

        # Declining trend
        cashflow = pd.DataFrame(
            {"Q1": [0.8e9], "Q2": [1.0e9]},  # Q1 < Q2 by >10%
            index=["Free Cash Flow"]
        )
        result = validate_cashflow_data(cashflow, "TEST")
        assert result.fcf_trend == "declining"


class TestCompanyDataValidation:
    """Test composite company data validation."""

    def test_full_validation(self):
        """Test full company data validation."""
        info = {
            "currentPrice": 150.0,
            "sharesOutstanding": 16000000000,
            "marketCap": 2400000000000,
            "beta": 1.2,
            "sector": "Technology",
        }
        cashflow = pd.DataFrame(
            {"Q1": [1e9], "Q2": [1.1e9], "Q3": [1.2e9], "Q4": [1.3e9]},
            index=["Free Cash Flow"]
        )

        validated_info, validated_cf = validate_company_data(info, cashflow, "AAPL")

        assert validated_info is not None
        assert validated_info.ticker == "AAPL"
        assert validated_cf is not None
        assert validated_cf.fcf_annual > 0

    def test_missing_cashflow_allowed(self):
        """Test that missing cashflow is allowed (for EV/Sales)."""
        info = {
            "currentPrice": 150.0,
            "sharesOutstanding": 16000000000,
        }

        validated_info, validated_cf = validate_company_data(info, None, "RIVN")

        assert validated_info is not None
        assert validated_cf is None  # No cashflow, but validation passes
