"""
Backtest Performance Analysis
==============================

Calculate and analyze backtest performance metrics:
- Information Coefficient (IC): Signal-return correlation
- Sharpe Ratio: Risk-adjusted returns
- Win Rate: % of correct predictions
- Quintile Analysis: Top vs bottom stock performance
- Hit Rate by Signal: Buy/Sell accuracy
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from src.backtest.config import backtest_config
from src.backtest.engine import BacktestResults
from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for backtest results."""

    # Information Coefficient (signal-return correlation)
    ic_1m: float
    ic_3m: float
    ic_6m: float
    ic_1y: float
    ic_3y: float
    ic_5y: float
    
    # Win rates (% of correct predictions)
    win_rate_1y: float
    win_rate_3y: float
    win_rate_5y: float
    
    # Signal accuracy
    buy_signal_win_rate_1y: float
    sell_signal_win_rate_1y: float
    
    # Quintile analysis (top 20% vs bottom 20%)
    top_quintile_return_1y: float
    bottom_quintile_return_1y: float
    quintile_spread_1y: float
    
    # Sharpe ratios
    sharpe_ratio_1y: float
    sharpe_ratio_3y: float
    sharpe_ratio_5y: float
    
    # Count statistics
    total_signals: int
    buy_signals: int
    sell_signals: int
    hold_signals: int
    
    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'ic_1m': self.ic_1m,
            'ic_3m': self.ic_3m,
            'ic_6m': self.ic_6m,
            'ic_1y': self.ic_1y,
            'ic_3y': self.ic_3y,
            'ic_5y': self.ic_5y,
            'win_rate_1y': self.win_rate_1y,
            'win_rate_3y': self.win_rate_3y,
            'win_rate_5y': self.win_rate_5y,
            'buy_signal_win_rate_1y': self.buy_signal_win_rate_1y,
            'sell_signal_win_rate_1y': self.sell_signal_win_rate_1y,
            'top_quintile_return_1y': self.top_quintile_return_1y,
            'bottom_quintile_return_1y': self.bottom_quintile_return_1y,
            'quintile_spread_1y': self.quintile_spread_1y,
            'sharpe_ratio_1y': self.sharpe_ratio_1y,
            'sharpe_ratio_3y': self.sharpe_ratio_3y,
            'sharpe_ratio_5y': self.sharpe_ratio_5y,
            'total_signals': self.total_signals,
            'buy_signals': self.buy_signals,
            'sell_signals': self.sell_signals,
            'hold_signals': self.hold_signals,
        }


class BacktestAnalyzer:
    """Analyze backtest results and calculate performance metrics."""

    def __init__(self, config: Any = None):
        """
        Initialize analyzer.

        Parameters
        ----------
        config : BacktestConfig, optional
            Configuration object. Uses global config if not provided.
        """
        self.config = config or backtest_config

    def _calculate_ic(self, signals: pd.Series, returns: pd.Series) -> float:
        """
        Calculate Information Coefficient (rank correlation).

        Parameters
        ----------
        signals : pd.Series
            Model signals (upside predictions)
        returns : pd.Series
            Actual forward returns

        Returns
        -------
        float
            Spearman rank correlation coefficient
        """
        # Remove NaN values
        valid_mask = ~(signals.isna() | returns.isna())
        signals_clean = signals[valid_mask]
        returns_clean = returns[valid_mask]
        
        if len(signals_clean) < 10:  # Need minimum sample size
            return np.nan
        
        # Spearman correlation (rank-based, robust to outliers)
        correlation, _ = stats.spearmanr(signals_clean, returns_clean)
        return correlation

    def _calculate_win_rate(self, signals: pd.Series, returns: pd.Series) -> float:
        """
        Calculate win rate (% of positive predictions that were correct).

        Parameters
        ----------
        signals : pd.Series
            Model signals (positive = buy, negative = sell)
        returns : pd.Series
            Actual forward returns

        Returns
        -------
        float
            Win rate as percentage (0-100)
        """
        valid_mask = ~(signals.isna() | returns.isna())
        signals_clean = signals[valid_mask]
        returns_clean = returns[valid_mask]
        
        if len(signals_clean) == 0:
            return np.nan
        
        # Count correct predictions
        correct = ((signals_clean > 0) & (returns_clean > 0)) | ((signals_clean < 0) & (returns_clean < 0))
        win_rate = correct.sum() / len(correct) * 100
        
        return win_rate

    def _calculate_quintile_analysis(self, df: pd.DataFrame, return_col: str) -> tuple[float, float, float]:
        """
        Calculate top vs bottom quintile returns.

        Parameters
        ----------
        df : pd.DataFrame
            Backtest results dataframe
        return_col : str
            Return column to analyze (e.g., 'actual_1y')

        Returns
        -------
        tuple
            (top_quintile_return, bottom_quintile_return, spread)
        """
        valid_df = df[~df[return_col].isna()].copy()
        
        if len(valid_df) < 20:  # Need reasonable sample size
            return np.nan, np.nan, np.nan
        
        # Sort by predicted upside
        valid_df = valid_df.sort_values('upside_pct', ascending=False)
        
        # Top 20% and bottom 20%
        quintile_size = len(valid_df) // 5
        top_quintile = valid_df.head(quintile_size)
        bottom_quintile = valid_df.tail(quintile_size)
        
        top_return = top_quintile[return_col].mean() * 100  # Convert to percentage
        bottom_return = bottom_quintile[return_col].mean() * 100
        spread = top_return - bottom_return
        
        return top_return, bottom_return, spread

    def _calculate_sharpe_ratio(self, returns: pd.Series, annualization_factor: float = 1.0) -> float:
        """
        Calculate Sharpe ratio.

        Parameters
        ----------
        returns : pd.Series
            Series of returns
        annualization_factor : float
            Factor to annualize returns (1.0 for annual, sqrt(252) for daily)

        Returns
        -------
        float
            Sharpe ratio
        """
        returns_clean = returns.dropna()
        
        if len(returns_clean) < 10:
            return np.nan
        
        mean_return = returns_clean.mean()
        std_return = returns_clean.std()
        
        if std_return == 0:
            return np.nan
        
        # Risk-free rate from config
        risk_free = self.config.RISK_FREE_RATE * annualization_factor
        
        sharpe = (mean_return - risk_free) / std_return
        return sharpe

    def analyze(self, results: BacktestResults) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.

        Parameters
        ----------
        results : BacktestResults
            Backtest results to analyze

        Returns
        -------
        PerformanceMetrics
            Complete performance metrics
        """
        logger.info("Analyzing backtest results...")
        
        # Convert to DataFrame for analysis
        df = results.to_dataframe()
        
        # Handle empty results
        if len(df) == 0:
            logger.warning("No signals generated - returning zero metrics")
            return PerformanceMetrics(
                ic_1m=0.0, ic_3m=0.0, ic_6m=0.0, ic_1y=0.0, ic_3y=0.0, ic_5y=0.0,
                win_rate_1y=0.0, win_rate_3y=0.0, win_rate_5y=0.0,
                buy_signal_win_rate_1y=0.0, sell_signal_win_rate_1y=0.0,
                top_quintile_return_1y=0.0, bottom_quintile_return_1y=0.0, quintile_spread_1y=0.0,
                sharpe_ratio_1y=0.0, sharpe_ratio_3y=0.0, sharpe_ratio_5y=0.0,
                total_signals=0, buy_signals=0, sell_signals=0, hold_signals=0,
            )
        
        # Information Coefficients (IC)
        ic_1m = self._calculate_ic(df['upside_pct'], df['actual_1m'])
        ic_3m = self._calculate_ic(df['upside_pct'], df['actual_3m'])
        ic_6m = self._calculate_ic(df['upside_pct'], df['actual_6m'])
        ic_1y = self._calculate_ic(df['upside_pct'], df['actual_1y'])
        ic_3y = self._calculate_ic(df['upside_pct'], df['actual_3y'])
        ic_5y = self._calculate_ic(df['upside_pct'], df['actual_5y'])
        
        # Win rates
        win_rate_1y = self._calculate_win_rate(df['upside_pct'], df['actual_1y'])
        win_rate_3y = self._calculate_win_rate(df['upside_pct'], df['actual_3y'])
        win_rate_5y = self._calculate_win_rate(df['upside_pct'], df['actual_5y'])
        
        # Signal-specific win rates
        buy_df = df[df['signal'] == 'buy']
        sell_df = df[df['signal'] == 'sell']
        
        buy_win_rate_1y = ((buy_df['actual_1y'] > 0).sum() / len(buy_df) * 100) if len(buy_df) > 0 else np.nan
        sell_win_rate_1y = ((sell_df['actual_1y'] < 0).sum() / len(sell_df) * 100) if len(sell_df) > 0 else np.nan
        
        # Quintile analysis
        top_q_1y, bottom_q_1y, spread_1y = self._calculate_quintile_analysis(df, 'actual_1y')
        
        # Sharpe ratios
        sharpe_1y = self._calculate_sharpe_ratio(df['actual_1y'], annualization_factor=1.0)
        sharpe_3y = self._calculate_sharpe_ratio(df['actual_3y'], annualization_factor=1.0)
        sharpe_5y = self._calculate_sharpe_ratio(df['actual_5y'], annualization_factor=1.0)
        
        # Signal counts
        total_signals = len(df)
        buy_signals = (df['signal'] == 'buy').sum()
        sell_signals = (df['signal'] == 'sell').sum()
        hold_signals = (df['signal'] == 'hold').sum()
        
        metrics = PerformanceMetrics(
            ic_1m=ic_1m if not np.isnan(ic_1m) else 0.0,
            ic_3m=ic_3m if not np.isnan(ic_3m) else 0.0,
            ic_6m=ic_6m if not np.isnan(ic_6m) else 0.0,
            ic_1y=ic_1y if not np.isnan(ic_1y) else 0.0,
            ic_3y=ic_3y if not np.isnan(ic_3y) else 0.0,
            ic_5y=ic_5y if not np.isnan(ic_5y) else 0.0,
            win_rate_1y=win_rate_1y if not np.isnan(win_rate_1y) else 0.0,
            win_rate_3y=win_rate_3y if not np.isnan(win_rate_3y) else 0.0,
            win_rate_5y=win_rate_5y if not np.isnan(win_rate_5y) else 0.0,
            buy_signal_win_rate_1y=buy_win_rate_1y if not np.isnan(buy_win_rate_1y) else 0.0,
            sell_signal_win_rate_1y=sell_win_rate_1y if not np.isnan(sell_win_rate_1y) else 0.0,
            top_quintile_return_1y=top_q_1y if not np.isnan(top_q_1y) else 0.0,
            bottom_quintile_return_1y=bottom_q_1y if not np.isnan(bottom_q_1y) else 0.0,
            quintile_spread_1y=spread_1y if not np.isnan(spread_1y) else 0.0,
            sharpe_ratio_1y=sharpe_1y if not np.isnan(sharpe_1y) else 0.0,
            sharpe_ratio_3y=sharpe_3y if not np.isnan(sharpe_3y) else 0.0,
            sharpe_ratio_5y=sharpe_5y if not np.isnan(sharpe_5y) else 0.0,
            total_signals=total_signals,
            buy_signals=int(buy_signals),
            sell_signals=int(sell_signals),
            hold_signals=int(hold_signals),
        )
        
        logger.info("Analysis complete")
        return metrics

    def print_metrics(self, metrics: PerformanceMetrics) -> None:
        """
        Print formatted performance metrics.

        Parameters
        ----------
        metrics : PerformanceMetrics
            Metrics to display
        """
        print("\n" + "="*80)
        print("BACKTEST PERFORMANCE METRICS")
        print("="*80)
        
        print("\n📊 INFORMATION COEFFICIENT (IC) - Signal-Return Correlation")
        print(f"  1-Month:   {metrics.ic_1m:.4f}")
        print(f"  3-Month:   {metrics.ic_3m:.4f}")
        print(f"  6-Month:   {metrics.ic_6m:.4f}")
        print(f"  1-Year:    {metrics.ic_1y:.4f}")
        print(f"  3-Year:    {metrics.ic_3y:.4f}")
        print(f"  5-Year:    {metrics.ic_5y:.4f}")
        print(f"\n  ℹ️  IC > 0.05 is good, IC > 0.10 is excellent")
        
        print("\n✅ WIN RATES - % Correct Predictions")
        print(f"  1-Year:    {metrics.win_rate_1y:.1f}%")
        print(f"  3-Year:    {metrics.win_rate_3y:.1f}%")
        print(f"  5-Year:    {metrics.win_rate_5y:.1f}%")
        print(f"\n  ℹ️  >50% is better than random, >60% is strong")
        
        print("\n🎯 SIGNAL ACCURACY - By Signal Type (1Y)")
        print(f"  Buy Signals:   {metrics.buy_signal_win_rate_1y:.1f}% positive")
        print(f"  Sell Signals:  {metrics.sell_signal_win_rate_1y:.1f}% negative")
        
        print("\n📈 QUINTILE ANALYSIS - Top 20% vs Bottom 20% (1Y)")
        print(f"  Top Quintile:      {metrics.top_quintile_return_1y:+.1f}%")
        print(f"  Bottom Quintile:   {metrics.bottom_quintile_return_1y:+.1f}%")
        print(f"  Spread:            {metrics.quintile_spread_1y:+.1f}%")
        print(f"\n  ℹ️  Positive spread means model selects outperformers")
        
        print("\n💎 SHARPE RATIOS - Risk-Adjusted Returns")
        print(f"  1-Year:    {metrics.sharpe_ratio_1y:.2f}")
        print(f"  3-Year:    {metrics.sharpe_ratio_3y:.2f}")
        print(f"  5-Year:    {metrics.sharpe_ratio_5y:.2f}")
        print(f"\n  ℹ️  >1.0 is good, >2.0 is excellent")
        
        print("\n📋 SIGNAL DISTRIBUTION")
        print(f"  Total Signals:  {metrics.total_signals}")
        if metrics.total_signals > 0:
            print(f"  Buy:            {metrics.buy_signals} ({metrics.buy_signals/metrics.total_signals*100:.1f}%)")
            print(f"  Hold:           {metrics.hold_signals} ({metrics.hold_signals/metrics.total_signals*100:.1f}%)")
            print(f"  Sell:           {metrics.sell_signals} ({metrics.sell_signals/metrics.total_signals*100:.1f}%)")
        else:
            print(f"  Buy:            0 (0.0%)")
            print(f"  Hold:           0 (0.0%)")
            print(f"  Sell:           0 (0.0%)")
        
        print("\n" + "="*80 + "\n")
