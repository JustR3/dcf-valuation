"""
Walk-Forward Backtesting Engine
================================

Simulates real-world DCF model deployment by:
1. Walking forward through time (quarterly rebalancing)
2. Running DCF valuations using only point-in-time data
3. Recording model signals and actual forward returns
4. Calculating performance metrics

Key Principles:
- No lookahead bias: Only use data available at valuation date
- Realistic trading: Quarterly rebalancing, transaction costs considered
- Multiple horizons: Test 1y, 3y, 5y forward returns
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from tqdm import tqdm

from src.backtest.config import backtest_config
from src.backtest.data_loader import HistoricalDataLoader
from src.dcf_engine import DCFEngine
from src.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestSignal:
    """Single valuation signal at a point in time."""

    date: datetime
    ticker: str
    intrinsic_value: float
    current_price: float
    upside_pct: float
    signal: str  # 'buy', 'hold', 'sell'
    wacc: float
    growth_rate: float
    terminal_growth: float
    fcf: float
    
    # Actual forward returns (filled in later)
    actual_1m: float | None = None
    actual_3m: float | None = None
    actual_6m: float | None = None
    actual_1y: float | None = None
    actual_3y: float | None = None
    actual_5y: float | None = None


@dataclass
class BacktestResults:
    """Complete backtest results."""

    signals: list[BacktestSignal]
    start_date: datetime
    end_date: datetime
    num_rebalances: int
    tickers: list[str]
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert signals to DataFrame for analysis."""
        data = []
        for signal in self.signals:
            data.append({
                'date': signal.date,
                'ticker': signal.ticker,
                'intrinsic_value': signal.intrinsic_value,
                'current_price': signal.current_price,
                'upside_pct': signal.upside_pct,
                'signal': signal.signal,
                'wacc': signal.wacc,
                'growth_rate': signal.growth_rate,
                'terminal_growth': signal.terminal_growth,
                'fcf': signal.fcf,
                'actual_1m': signal.actual_1m,
                'actual_3m': signal.actual_3m,
                'actual_6m': signal.actual_6m,
                'actual_1y': signal.actual_1y,
                'actual_3y': signal.actual_3y,
                'actual_5y': signal.actual_5y,
            })
        return pd.DataFrame(data)


class WalkForwardBacktest:
    """Walk-forward backtesting engine for DCF model."""

    def __init__(self, config: Any = None):
        """
        Initialize backtest engine.

        Parameters
        ----------
        config : BacktestConfig, optional
            Configuration object. Uses global config if not provided.
        """
        self.config = config or backtest_config
        self.loader = HistoricalDataLoader(config)

    def _get_rebalance_dates(self, start_date: datetime, end_date: datetime) -> list[datetime]:
        """
        Generate quarterly rebalance dates.

        Parameters
        ----------
        start_date : datetime
            Start of backtest period
        end_date : datetime
            End of backtest period

        Returns
        -------
        list[datetime]
            List of rebalance dates (quarter-ends)
        """
        rebalance_dates = []
        current_year = start_date.year
        
        # Start from first quarter after start_date
        quarters = [(3, 31), (6, 30), (9, 30), (12, 31)]
        
        while True:
            for month, day in quarters:
                rebalance_date = datetime(current_year, month, day)
                if start_date <= rebalance_date <= end_date:
                    rebalance_dates.append(rebalance_date)
            
            current_year += 1
            if datetime(current_year, 1, 1) > end_date:
                break
        
        return rebalance_dates

    def _get_available_data(self, ticker: str, as_of_date: datetime, 
                           prices: dict[str, pd.DataFrame],
                           financials: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
        """
        Get only data available as of valuation date (no lookahead).

        Parameters
        ----------
        ticker : str
            Stock ticker
        as_of_date : datetime
            Valuation date
        prices : dict
            Price data for all tickers
        financials : dict
            Financial data for all tickers

        Returns
        -------
        tuple
            (price_data, financial_data) or (None, None) if insufficient data
        """
        # Get price data up to (but not including) valuation date
        if ticker not in prices:
            return None, None
        
        price_df = prices[ticker]
        available_prices = price_df[price_df.index < as_of_date]
        
        if len(available_prices) < 60:  # Need at least 60 days (~3 months) of price history
            return None, None
        
        # Get financial data available as of date
        if ticker not in financials:
            return None, None
        
        financial_df = financials[ticker]
        available_financials = financial_df[financial_df.index < as_of_date]
        
        if len(available_financials) < 2:  # Need at least 2 quarters to calculate growth
            return None, None
        
        return available_prices, available_financials

    def _run_dcf_at_date(self, ticker: str, as_of_date: datetime,
                        price_data: pd.DataFrame,
                        financial_data: pd.DataFrame) -> BacktestSignal | None:
        """
        Run DCF valuation using only data available at specific date.

        Parameters
        ----------
        ticker : str
            Stock ticker
        as_of_date : datetime
            Valuation date
        price_data : pd.DataFrame
            Historical prices available at date
        financial_data : pd.DataFrame
            Historical financials available at date

        Returns
        -------
        BacktestSignal or None
            Valuation signal or None if valuation failed
        """
        try:
            # Get current price (last available price before valuation date)
            current_price = price_data['close'].iloc[-1]
            
            # Calculate historical growth from financials
            if 'fcf' in financial_data.columns:
                fcf_series = financial_data['fcf'].dropna()
                if len(fcf_series) >= 2:
                    # Calculate trailing growth rate
                    recent_fcf = fcf_series.iloc[-1]
                    old_fcf = fcf_series.iloc[-2]
                    if old_fcf > 0:
                        historical_growth = (recent_fcf - old_fcf) / old_fcf
                    else:
                        historical_growth = 0.05  # Default 5%
                else:
                    historical_growth = 0.05
            else:
                historical_growth = 0.05
            
            # Cap growth at reasonable bounds
            historical_growth = np.clip(historical_growth, -0.20, 0.50)
            
            # Run DCF engine (simplified version using available data)
            # In production, this would use actual DCFEngine with historical data
            # For now, simulate with basic DCF calculation
            
            # Get most recent FCF
            if 'fcf' in financial_data.columns:
                fcf = financial_data['fcf'].iloc[-1]
            else:
                logger.warning(f"No FCF data for {ticker} as of {as_of_date}")
                return None
            
            # Simple WACC estimation (in production, use actual calculation)
            wacc = 0.10  # Simplified for pilot
            
            # Terminal growth
            terminal_growth = 0.025  # GDP growth rate
            
            # Project 5 years of FCF
            years = 5
            projected_fcfs = []
            current_fcf = fcf
            for i in range(years):
                current_fcf *= (1 + historical_growth)
                discount_factor = (1 + wacc) ** (i + 1)
                pv = current_fcf / discount_factor
                projected_fcfs.append(pv)
            
            # Terminal value
            final_fcf = current_fcf * (1 + terminal_growth)
            terminal_value = final_fcf / (wacc - terminal_growth)
            terminal_pv = terminal_value / ((1 + wacc) ** years)
            
            # Enterprise value
            enterprise_value = sum(projected_fcfs) + terminal_pv
            
            # Intrinsic value per share (simplified - ignoring debt/cash)
            if 'shares_outstanding' in financial_data.columns:
                shares = financial_data['shares_outstanding'].iloc[-1]
                if shares > 0:
                    intrinsic_value = enterprise_value / shares
                else:
                    return None
            else:
                return None
            
            # Calculate upside
            upside_pct = (intrinsic_value - current_price) / current_price * 100
            
            # Generate signal
            if upside_pct >= self.config.BUY_THRESHOLD * 100:
                signal = 'buy'
            elif upside_pct <= self.config.SELL_THRESHOLD * 100:
                signal = 'sell'
            else:
                signal = 'hold'
            
            return BacktestSignal(
                date=as_of_date,
                ticker=ticker,
                intrinsic_value=intrinsic_value,
                current_price=current_price,
                upside_pct=upside_pct,
                signal=signal,
                wacc=wacc,
                growth_rate=historical_growth,
                terminal_growth=terminal_growth,
                fcf=fcf,
            )
            
        except Exception as e:
            logger.warning(f"DCF failed for {ticker} as of {as_of_date}: {e}")
            return None

    def _fill_forward_returns(self, signals: list[BacktestSignal], 
                             prices: dict[str, pd.DataFrame]) -> list[BacktestSignal]:
        """
        Fill in actual forward returns for each signal.

        Parameters
        ----------
        signals : list[BacktestSignal]
            Signals with missing forward returns
        prices : dict
            Price data with pre-calculated forward returns

        Returns
        -------
        list[BacktestSignal]
            Signals with forward returns filled in
        """
        for signal in signals:
            ticker = signal.ticker
            date = signal.date
            
            if ticker not in prices:
                continue
            
            price_df = prices[ticker]
            
            # Find exact date or nearest prior date
            available_dates = price_df[price_df.index <= date].index
            if len(available_dates) == 0:
                continue
            
            signal_date = available_dates[-1]
            
            # Get forward returns from that date
            if signal_date in price_df.index:
                row = price_df.loc[signal_date]
                signal.actual_1m = row.get('returns_1m')
                signal.actual_3m = row.get('returns_3m')
                signal.actual_6m = row.get('returns_6m')
                signal.actual_1y = row.get('returns_1y')
                signal.actual_3y = row.get('returns_3y')
                signal.actual_5y = row.get('returns_5y')
        
        return signals

    def run_backtest(self, tickers: list[str], start_date: datetime, 
                    end_date: datetime) -> BacktestResults:
        """
        Run walk-forward backtest on specified tickers and date range.

        Parameters
        ----------
        tickers : list[str]
            List of ticker symbols to backtest
        start_date : datetime
            Start of backtest period
        end_date : datetime
            End of backtest period

        Returns
        -------
        BacktestResults
            Complete backtest results with signals and returns
        """
        logger.info(f"Starting walk-forward backtest: {len(tickers)} tickers, {start_date.date()} to {end_date.date()}")
        
        # Load all historical data
        logger.info("Loading historical data...")
        prices = self.loader.download_prices(tickers, start_date, end_date)
        financials = self.loader.download_financials(tickers)
        
        # Generate rebalance dates
        rebalance_dates = self._get_rebalance_dates(start_date, end_date)
        logger.info(f"Generated {len(rebalance_dates)} rebalance dates")
        
        # Walk forward through time
        all_signals = []
        
        for rebalance_date in tqdm(rebalance_dates, desc="Running valuations"):
            logger.info(f"\nValuing stocks as of {rebalance_date.date()}")
            
            for ticker in tickers:
                # Get only data available at this date
                price_data, financial_data = self._get_available_data(
                    ticker, rebalance_date, prices, financials
                )
                
                if price_data is None or financial_data is None:
                    logger.debug(f"Insufficient data for {ticker} as of {rebalance_date.date()}")
                    continue
                
                # Run DCF valuation
                signal = self._run_dcf_at_date(ticker, rebalance_date, price_data, financial_data)
                
                if signal:
                    all_signals.append(signal)
                    logger.debug(f"{ticker}: ${signal.intrinsic_value:.2f} vs ${signal.current_price:.2f} ({signal.upside_pct:+.1f}%) -> {signal.signal}")
        
        logger.info(f"\nGenerated {len(all_signals)} valuation signals")
        
        # Fill in actual forward returns
        logger.info("Calculating actual forward returns...")
        all_signals = self._fill_forward_returns(all_signals, prices)
        
        results = BacktestResults(
            signals=all_signals,
            start_date=start_date,
            end_date=end_date,
            num_rebalances=len(rebalance_dates),
            tickers=tickers,
        )
        
        logger.info("Backtest complete!")
        return results

    def run_pilot(self) -> BacktestResults:
        """
        Run pilot backtest (5 stocks, 5 years).

        Returns
        -------
        BacktestResults
            Pilot backtest results
        """
        return self.run_backtest(
            tickers=self.config.PILOT_TICKERS,
            start_date=self.config.PILOT_START,
            end_date=self.config.PILOT_END,
        )

    def run_full(self) -> BacktestResults:
        """
        Run full backtest (50+ stocks, 15 years).

        Returns
        -------
        BacktestResults
            Full backtest results
        """
        return self.run_backtest(
            tickers=self.config.FULL_TEST_TICKERS,
            start_date=self.config.START_DATE,
            end_date=self.config.END_DATE,
        )
