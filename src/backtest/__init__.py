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

from src.backtest.config import BacktestConfig

__all__ = ["BacktestConfig"]
