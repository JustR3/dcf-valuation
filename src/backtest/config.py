"""Backtesting configuration and parameters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BacktestConfig:
    """Configuration for backtesting framework."""

    # Data Paths
    DATA_DIR: Path = Path("data/backtest")
    PRICES_DIR: Path = Path("data/backtest/prices")
    FINANCIALS_DIR: Path = Path("data/backtest/financials")
    MARKET_DATA_DIR: Path = Path("data/backtest/market_data")
    RESULTS_DIR: Path = Path("data/backtest/results")

    # Time Periods
    START_DATE: datetime = datetime(2010, 1, 1)  # Post-financial crisis
    END_DATE: datetime = datetime(2025, 12, 31)  # Current
    PILOT_START: datetime = datetime(2024, 1, 1)  # Pilot backtest start (recent data only from yfinance)
    PILOT_END: datetime = datetime(2024, 6, 30)  # Pilot backtest end (need forward data)

    # Forward Return Horizons (in trading days)
    FORWARD_PERIODS: dict[str, int] = None  # Will be set in __post_init__

    # Rebalancing
    REBALANCE_FREQUENCY: str = "quarterly"  # quarterly, monthly, annual
    QUARTERS: list[tuple[int, int]] = None  # Will be set in __post_init__

    # Data Collection
    BATCH_SIZE: int = 10  # Number of tickers to download at once
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0  # Seconds
    RATE_LIMIT_DELAY: float = 0.5  # Delay between API calls

    # Caching
    CACHE_ENABLED: bool = True
    FORCE_REFRESH: bool = False  # Force re-download even if cached

    # Pilot Test Parameters
    PILOT_TICKERS: list[str] = None  # Will be set in __post_init__

    # Full Test Parameters
    FULL_TEST_TICKERS: list[str] = None  # Will be set in __post_init__

    # Performance Analysis
    RISK_FREE_RATE: float = 0.04  # Annual risk-free rate for Sharpe calculation
    BENCHMARK_TICKER: str = "SPY"  # S&P 500 benchmark

    # Signal Thresholds (from DCF model)
    BUY_THRESHOLD: float = 0.15  # 15% upside to trigger buy signal
    SELL_THRESHOLD: float = -0.10  # -10% to trigger sell signal

    def __post_init__(self):
        """Initialize computed fields."""
        # Forward return periods (approximate trading days)
        self.FORWARD_PERIODS = {
            "1m": 21,  # 1 month
            "3m": 63,  # 3 months
            "6m": 126,  # 6 months
            "1y": 252,  # 1 year
            "3y": 756,  # 3 years
            "5y": 1260,  # 5 years
        }

        # Quarterly rebalance dates (end of Q1, Q2, Q3, Q4)
        self.QUARTERS = [(3, 31), (6, 30), (9, 30), (12, 31)]

        # Pilot test stocks (5 diverse stocks)
        self.PILOT_TICKERS = [
            "AAPL",  # Technology
            "JPM",  # Financial Services
            "XOM",  # Energy
            "WMT",  # Consumer Defensive
            "JNJ",  # Healthcare
        ]

        # Full backtest stocks (50+ stocks across all sectors)
        from src.config import SECTOR_PEERS

        self.FULL_TEST_TICKERS = []
        for sector, tickers in SECTOR_PEERS.items():
            # Take first 5 tickers from each sector (or fewer if not available)
            self.FULL_TEST_TICKERS.extend(tickers[:5])

        # Ensure directories exist
        for directory in [
            self.DATA_DIR,
            self.PRICES_DIR,
            self.FINANCIALS_DIR,
            self.MARKET_DATA_DIR,
            self.RESULTS_DIR,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


# Global config instance
backtest_config = BacktestConfig()
