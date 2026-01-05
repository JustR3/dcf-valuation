"""
Backtesting Framework for DCF Valuation Model
==============================================

Walk-forward backtesting to validate model predictive power using historical data.

Modules:
- data_loader: Historical data fetching and caching (prices, financials, market data)
- engine: Walk-forward backtest execution engine
- analysis: Performance metrics and attribution analysis
- config: Backtest configuration and parameters
"""

from src.backtest.analysis import BacktestAnalyzer, PerformanceMetrics
from src.backtest.config import BacktestConfig, backtest_config
from src.backtest.data_loader import HistoricalDataLoader
from src.backtest.engine import BacktestResults, BacktestSignal, WalkForwardBacktest

__all__ = [
    "BacktestConfig",
    "backtest_config",
    "HistoricalDataLoader",
    "WalkForwardBacktest",
    "BacktestSignal",
    "BacktestResults",
    "BacktestAnalyzer",
    "PerformanceMetrics",
]
