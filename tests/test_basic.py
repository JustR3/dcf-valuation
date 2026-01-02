"""Basic unit tests for DCF Valuation Toolkit."""

from datetime import datetime

import pandas as pd
import pytest

from src.config import config
from src.dcf_engine import CompanyData, DCFEngine
from src.optimizer import OptimizationMethod, PortfolioEngine, PortfolioMetrics
from src.regime import MarketRegime, RegimeDetector
from src.utils import DataCache, RateLimiter


class TestConfig:
    """Test configuration constants."""

    def test_config_values(self):
        """Test that config has expected values."""
        assert config.RISK_FREE_RATE > 0
        assert config.MARKET_RISK_PREMIUM > 0
        assert config.MIN_GROWTH_RATE < 0
        assert config.MAX_GROWTH_RATE > 0
        assert config.MONTE_CARLO_ITERATIONS >= 1000

    def test_config_sector_priors(self):
        """Test sector growth priors are properly defined."""
        assert "Technology" in config.SECTOR_GROWTH_PRIORS
        assert "Healthcare" in config.SECTOR_GROWTH_PRIORS
        assert len(config.SECTOR_GROWTH_PRIORS) > 0


class TestCompanyData:
    """Test CompanyData dataclass."""

    def test_company_data_creation(self):
        """Test creating CompanyData instance."""
        data = CompanyData(
            ticker="AAPL",
            fcf=100000.0,
            shares=16000.0,
            current_price=180.0,
            market_cap=2880.0,
            beta=1.2,
            analyst_growth=0.15,
            revenue=400000.0,
            sector="Technology"
        )
        assert data.ticker == "AAPL"
        assert data.fcf == 100000.0
        assert data.beta == 1.2

    def test_company_data_to_dict(self):
        """Test converting CompanyData to dict."""
        data = CompanyData(
            ticker="MSFT",
            fcf=80000.0,
            shares=7500.0,
            current_price=380.0,
            market_cap=2850.0,
            beta=1.1
        )
        result = data.to_dict()
        assert isinstance(result, dict)
        assert result["ticker"] == "MSFT"
        assert result["fcf"] == 80000.0


class TestDCFEngine:
    """Test DCF Engine functionality."""

    def test_dcf_engine_initialization(self):
        """Test DCFEngine initialization."""
        engine = DCFEngine("AAPL", auto_fetch=False)
        assert engine.ticker == "AAPL"
        assert engine.is_ready is False
        assert engine.company_data is None

    def test_dcf_wacc_calculation(self):
        """Test WACC calculation with static mode (no FRED/CAPE)."""
        engine = DCFEngine("TEST", auto_fetch=False)
        # Mock company data
        engine._company_data = CompanyData(
            ticker="TEST",
            fcf=10000.0,
            shares=1000.0,
            current_price=100.0,
            market_cap=100.0,
            beta=1.5
        )
        # Use static mode to test core CAPM calculation without dynamic data
        wacc = engine.calculate_wacc(use_dynamic_rf=False, use_cape_adjustment=False)
        # WACC = risk_free + beta * market_risk_premium
        expected = config.RISK_FREE_RATE + 1.5 * config.MARKET_RISK_PREMIUM
        assert abs(wacc - expected) < 0.001

    def test_dcf_growth_rate_validation(self):
        """Test growth rate cleaning with Bayesian priors."""
        engine = DCFEngine("TEST", auto_fetch=False)
        engine._company_data = CompanyData(
            ticker="TEST",
            fcf=10000.0,
            shares=1000.0,
            current_price=100.0,
            market_cap=100.0,
            beta=1.0,
            analyst_growth=0.15,
            sector="Technology"
        )

        # Test valid growth - should return as-is
        growth, msg = engine.clean_growth_rate(0.10, "Technology")
        assert growth == 0.10

        # Test extreme growth (should blend with prior)
        growth, msg = engine.clean_growth_rate(0.60, "Technology")
        assert growth < 0.60  # Should be pulled down by prior
        # Note: Prior may come from Damodaran (dynamic) or static config
        # Just verify it's reasonable
        assert 0.10 <= growth <= 0.50  # Reasonable blended range

        # Test None growth (should use sector prior from Damodaran or config)
        growth, msg = engine.clean_growth_rate(None, "Technology")
        # Prior could be from Damodaran (~12%) or config (15%)
        assert 0.05 <= growth <= 0.20  # Reasonable prior range


class TestOptimizationMethod:
    """Test OptimizationMethod enum."""

    def test_optimization_methods_exist(self):
        """Test that all optimization methods are defined."""
        assert OptimizationMethod.MAX_SHARPE
        assert OptimizationMethod.MIN_VOLATILITY
        assert OptimizationMethod.EFFICIENT_RISK
        assert OptimizationMethod.MAX_QUADRATIC_UTILITY


class TestPortfolioMetrics:
    """Test PortfolioMetrics dataclass."""

    def test_portfolio_metrics_creation(self):
        """Test creating PortfolioMetrics instance."""
        metrics = PortfolioMetrics(
            expected_annual_return=12.5,
            annual_volatility=18.0,
            sharpe_ratio=0.65,
            weights={"AAPL": 0.3, "MSFT": 0.3, "GOOGL": 0.4},
            optimization_method="max_sharpe"
        )
        assert metrics.expected_annual_return == 12.5
        assert metrics.sharpe_ratio == 0.65
        assert len(metrics.weights) == 3

    def test_portfolio_metrics_to_dict(self):
        """Test converting metrics to dict."""
        metrics = PortfolioMetrics(
            expected_annual_return=15.0,
            annual_volatility=20.0,
            sharpe_ratio=0.70,
            weights={"AAPL": 0.5, "GOOGL": 0.5},
            optimization_method="min_volatility",
            sortino_ratio=0.85,
            max_drawdown=-0.15
        )
        result = metrics.to_dict()
        assert isinstance(result, dict)
        assert result["expected_annual_return"] == 15.0
        assert result["sortino_ratio"] == 0.85


class TestPortfolioEngine:
    """Test Portfolio Engine (without API calls)."""

    def test_portfolio_engine_initialization(self):
        """Test PortfolioEngine initialization."""
        engine = PortfolioEngine(["AAPL", "MSFT", "GOOGL"])
        assert len(engine.tickers) == 3
        assert engine.tickers[0] == "AAPL"
        assert engine.prices is None
        assert engine.optimized_weights is None


class TestMarketRegime:
    """Test MarketRegime enum."""

    def test_regime_types(self):
        """Test that all regime types are defined."""
        assert MarketRegime.RISK_ON
        assert MarketRegime.RISK_OFF
        assert MarketRegime.CAUTION
        assert MarketRegime.UNKNOWN

    def test_regime_is_bullish(self):
        """Test is_bullish property."""
        assert MarketRegime.RISK_ON.is_bullish is True
        assert MarketRegime.RISK_OFF.is_bullish is False
        assert MarketRegime.CAUTION.is_bullish is False


class TestRegimeDetector:
    """Test RegimeDetector (without API calls)."""

    def test_regime_detector_initialization(self):
        """Test RegimeDetector initialization."""
        detector = RegimeDetector(ticker="SPY", lookback_days=300)
        assert detector.ticker == "SPY"
        assert detector.lookback_days == 300
        assert detector.last_error is None


class TestDataCache:
    """Test DataCache utility."""

    def test_cache_initialization(self):
        """Test cache initialization."""
        cache = DataCache(cache_dir="data/cache/test", default_expiry_hours=24)
        assert cache.default_expiry_hours == 24
        assert cache.cache_dir.name == "test"

    def test_cache_set_and_get(self):
        """Test caching data."""
        cache = DataCache(cache_dir="data/cache/test", default_expiry_hours=24)

        # Test dict caching
        test_data = {"ticker": "AAPL", "price": 180.0}
        cache.set("test_key", test_data)
        result = cache.get("test_key")
        assert result == test_data

        # Clean up
        cache.invalidate("test_key")

    def test_cache_dataframe(self):
        """Test caching pandas DataFrame."""
        cache = DataCache(cache_dir="data/cache/test", default_expiry_hours=24)

        df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        cache.set("test_df", df)
        result = cache.get("test_df")

        assert isinstance(result, pd.DataFrame)
        assert result.shape == df.shape

        # Clean up
        cache.invalidate("test_df")


class TestRateLimiter:
    """Test RateLimiter utility."""

    def test_rate_limiter_initialization(self):
        """Test RateLimiter initialization."""
        limiter = RateLimiter(calls_per_minute=60)
        assert limiter.min_interval == 1.0

    def test_rate_limiter_wait(self):
        """Test rate limiter wait functionality."""
        limiter = RateLimiter(calls_per_minute=120)  # Fast for testing
        start = datetime.now()
        limiter.wait()
        limiter.wait()
        elapsed = (datetime.now() - start).total_seconds()
        # Should be at least one interval
        assert elapsed >= limiter.min_interval


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
