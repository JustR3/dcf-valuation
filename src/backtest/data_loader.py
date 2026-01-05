"""
Historical Data Loader for Backtesting
======================================

Fetches and caches historical price and financial data for backtesting.

Features:
- Bulk downloading with rate limiting
- Parquet-based caching per ticker
- Forward returns pre-calculation
- Resume capability from checkpoints
- Exponential backoff retry logic
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from src.backtest.config import backtest_config
from src.external.xbrl_parser import XBRLDirectParser
from src.logging_config import get_logger

logger = get_logger(__name__)


class HistoricalDataLoader:
    """Load and cache historical stock data for backtesting."""

    def __init__(self, config: Any = None):
        """
        Initialize data loader.

        Parameters
        ----------
        config : BacktestConfig, optional
            Configuration object. Uses global config if not provided.
        """
        self.config = config or backtest_config
        self.metadata_file = self.config.PRICES_DIR / "index.json"
        self._load_metadata()

        # Initialize XBRL parser for financial data
        self.xbrl_parser = XBRLDirectParser()

    def _load_metadata(self) -> None:
        """Load metadata about cached files."""
        if self.metadata_file.exists():
            with open(self.metadata_file) as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {}

    def _save_metadata(self) -> None:
        """Save metadata about cached files."""
        with open(self.metadata_file, "w") as f:
            json.dump(self.metadata, f, indent=2, default=str)

    def _get_cache_path(self, ticker: str, data_type: str = "prices") -> Path:
        """
        Get cache file path for ticker.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        data_type : str
            'prices', 'financials', or 'financials_xbrl'

        Returns
        -------
        Path
            Path to parquet cache file
        """
        if data_type == "prices":
            return self.config.PRICES_DIR / f"{ticker}_daily.parquet"
        elif data_type == "financials":
            return self.config.FINANCIALS_DIR / f"{ticker}_quarterly.parquet"
        elif data_type == "financials_xbrl":
            return self.config.FINANCIALS_DIR / f"{ticker}_annual_xbrl.parquet"
        else:
            raise ValueError(f"Unknown data_type: {data_type}")

    def _is_cached(self, ticker: str, data_type: str = "prices") -> bool:
        """Check if ticker data is cached and up to date."""
        if self.config.FORCE_REFRESH:
            return False

        cache_path = self._get_cache_path(ticker, data_type)
        if not cache_path.exists():
            return False

        # Check metadata for last update
        meta_key = f"{ticker}_{data_type}"
        if meta_key not in self.metadata:
            return False

        last_update = datetime.fromisoformat(self.metadata[meta_key]["last_update"])
        days_old = (datetime.now() - last_update).days

        # Price data: refresh if older than 1 day
        # Financial data: refresh if older than 7 days
        max_age = 1 if data_type == "prices" else 7
        return days_old < max_age

    def _calculate_forward_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate forward returns for various horizons.

        Parameters
        ----------
        df : pd.DataFrame
            Price data with 'close' column

        Returns
        -------
        pd.DataFrame
            Data with added forward return columns
        """
        for period_name, days in self.config.FORWARD_PERIODS.items():
            # Shift prices backwards to get future prices
            future_price = df["close"].shift(-days)
            df[f"returns_{period_name}"] = (future_price - df["close"]) / df["close"]

        return df

    def download_prices(
        self, tickers: list[str], start_date: datetime | None = None, end_date: datetime | None = None
    ) -> dict[str, pd.DataFrame]:
        """
        Download historical price data for multiple tickers.

        Uses bulk download for efficiency, with caching and retry logic.

        Parameters
        ----------
        tickers : list[str]
            List of ticker symbols
        start_date : datetime, optional
            Start date for historical data. Defaults to config.START_DATE
        end_date : datetime, optional
            End date for historical data. Defaults to config.END_DATE

        Returns
        -------
        dict[str, pd.DataFrame]
            Dictionary mapping ticker to price DataFrame
        """
        start_date = start_date or self.config.START_DATE
        end_date = end_date or self.config.END_DATE

        logger.info(f"Downloading price data for {len(tickers)} tickers from {start_date.date()} to {end_date.date()}")

        results = {}
        tickers_to_download = []

        # Check cache first
        for ticker in tickers:
            if self._is_cached(ticker, "prices"):
                logger.debug(f"Loading {ticker} from cache")
                try:
                    df = pd.read_parquet(self._get_cache_path(ticker, "prices"))
                    results[ticker] = df
                except Exception as e:
                    logger.warning(f"Failed to load {ticker} from cache: {e}")
                    tickers_to_download.append(ticker)
            else:
                tickers_to_download.append(ticker)

        if not tickers_to_download:
            logger.info("All tickers loaded from cache")
            return results

        logger.info(f"Downloading {len(tickers_to_download)} tickers from yfinance")

        # Download in batches with progress bar
        for i in tqdm(range(0, len(tickers_to_download), self.config.BATCH_SIZE), desc="Downloading prices"):
            batch = tickers_to_download[i : i + self.config.BATCH_SIZE]

            # Retry logic with exponential backoff
            for attempt in range(self.config.MAX_RETRIES):
                try:
                    # Bulk download (much faster than individual calls)
                    data = yf.download(
                        batch,
                        start=start_date,
                        end=end_date,
                        progress=False,
                        group_by="ticker",
                        auto_adjust=True,  # Adjust for splits/dividends
                    )

                    # Process each ticker in batch
                    for ticker in batch:
                        try:
                            if len(batch) == 1:
                                ticker_data = data
                            else:
                                ticker_data = data[ticker]

                            if ticker_data.empty:
                                logger.warning(f"No data returned for {ticker}")
                                continue

                            # Rename columns to lowercase
                            ticker_data.columns = [col.lower() for col in ticker_data.columns]

                            # Calculate forward returns
                            ticker_data = self._calculate_forward_returns(ticker_data)

                            # Save to cache
                            cache_path = self._get_cache_path(ticker, "prices")
                            ticker_data.to_parquet(cache_path)

                            # Update metadata
                            self.metadata[f"{ticker}_prices"] = {
                                "last_update": datetime.now().isoformat(),
                                "start_date": ticker_data.index.min().isoformat(),
                                "end_date": ticker_data.index.max().isoformat(),
                                "num_records": len(ticker_data),
                            }

                            results[ticker] = ticker_data
                            logger.debug(f"Downloaded and cached {ticker}: {len(ticker_data)} records")

                        except Exception as e:
                            logger.error(f"Error processing {ticker}: {e}")

                    # Success - break retry loop
                    break

                except Exception as e:
                    if attempt < self.config.MAX_RETRIES - 1:
                        wait_time = self.config.RETRY_DELAY * (2**attempt)
                        logger.warning(f"Batch download failed (attempt {attempt + 1}): {e}. Retrying in {wait_time}s")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"Batch download failed after {self.config.MAX_RETRIES} attempts: {e}")

            # Rate limiting between batches
            time.sleep(self.config.RATE_LIMIT_DELAY)

        # Save updated metadata
        self._save_metadata()

        logger.info(f"Successfully downloaded {len(results)} / {len(tickers)} tickers")
        return results

    def download_financials(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        """
        Download historical annual financial data using SEC XBRL.

        Uses SEC Company Facts API to get 10-15+ years of financial data,
        significantly more than yfinance's ~6 quarters.

        Parameters
        ----------
        tickers : list[str]
            List of ticker symbols

        Returns
        -------
        dict[str, pd.DataFrame]
            Dictionary mapping ticker to financials DataFrame
        """
        logger.info(f"Downloading financial data for {len(tickers)} tickers using SEC XBRL")

        results = {}

        for ticker in tqdm(tickers, desc="Downloading financials"):
            # Check cache
            if self._is_cached(ticker, "financials_xbrl"):
                logger.debug(f"Loading {ticker} financials from cache")
                try:
                    df = pd.read_parquet(self._get_cache_path(ticker, "financials_xbrl"))
                    # Ensure index is datetime (not string)
                    if not isinstance(df.index, pd.DatetimeIndex):
                        df.index = pd.to_datetime(df.index)
                    results[ticker] = df
                    continue
                except Exception as e:
                    logger.warning(f"Failed to load {ticker} financials from cache: {e}")

            # Download with retry logic
            for attempt in range(self.config.MAX_RETRIES):
                try:
                    # Use XBRL parser to get annual 10-K data
                    df = self.xbrl_parser.get_financials(ticker, form_type="10-K")

                    if df.empty:
                        logger.warning(f"No financial data available for {ticker}")
                        break

                    # Rename columns to match expected format
                    # XBRL columns: revenue, net_income, operating_cash_flow, capex,
                    #               total_debt, cash, shares_outstanding, free_cash_flow
                    # Expected: revenue, operating_income, net_income, fcf, total_debt,
                    #           cash, shares_outstanding

                    # Map XBRL columns to expected columns
                    column_mapping = {
                        "free_cash_flow": "fcf",
                        # Keep other columns as-is: revenue, net_income, total_debt, cash, shares_outstanding
                    }

                    df = df.rename(columns=column_mapping)

                    # Filter by date range if specified in config
                    if hasattr(self.config, "START_DATE") and self.config.START_DATE:
                        df = df[df.index >= pd.to_datetime(self.config.START_DATE)]
                    if hasattr(self.config, "END_DATE") and self.config.END_DATE:
                        df = df[df.index <= pd.to_datetime(self.config.END_DATE)]

                    # Ensure index is datetime and sorted
                    df.index = pd.to_datetime(df.index)
                    df = df.sort_index(ascending=True)

                    # Save to cache with xbrl identifier
                    cache_path = self._get_cache_path(ticker, "financials_xbrl")
                    df.to_parquet(cache_path)

                    # Update metadata
                    self.metadata[f"{ticker}_financials_xbrl"] = {
                        "last_update": datetime.now().isoformat(),
                        "earliest_date": str(df.index.min().date() if hasattr(df.index.min(), 'date') else df.index.min()),
                        "latest_date": str(df.index.max().date() if hasattr(df.index.max(), 'date') else df.index.max()),
                        "num_periods": len(df),
                        "source": "xbrl",
                    }

                    results[ticker] = df
                    logger.debug(
                        f"Downloaded and cached {ticker} financials: {len(df)} periods "
                        f"({df.index.min().year}-{df.index.max().year})"
                    )

                    break  # Success

                except Exception as e:
                    if attempt < self.config.MAX_RETRIES - 1:
                        wait_time = self.config.RETRY_DELAY * (2**attempt)
                        logger.warning(
                            f"Failed to download {ticker} financials (attempt {attempt + 1}): {e}. "
                            f"Retrying in {wait_time}s"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to download {ticker} financials after "
                            f"{self.config.MAX_RETRIES} attempts: {e}"
                        )

            # Rate limiting (SEC requests)
            time.sleep(self.config.RATE_LIMIT_DELAY)

        # Save metadata
        self._save_metadata()

        logger.info(
            f"Successfully downloaded financials for {len(results)} / {len(tickers)} tickers"
        )

        return results

    def get_market_data(self, start_date: datetime | None = None, end_date: datetime | None = None) -> pd.DataFrame:
        """
        Download risk-free rate and market benchmark data.

        Parameters
        ----------
        start_date : datetime, optional
            Start date. Defaults to config.START_DATE
        end_date : datetime, optional
            End date. Defaults to config.END_DATE

        Returns
        -------
        pd.DataFrame
            Market data with risk_free_rate and benchmark_returns
        """
        start_date = start_date or self.config.START_DATE
        end_date = end_date or self.config.END_DATE

        cache_path = self.config.MARKET_DATA_DIR / "market_data.parquet"

        # Check cache
        if cache_path.exists() and not self.config.FORCE_REFRESH:
            logger.info("Loading market data from cache")
            return pd.read_parquet(cache_path)

        logger.info("Downloading market data (risk-free rate and benchmark)")

        # Download benchmark (SPY or similar)
        benchmark = yf.download(self.config.BENCHMARK_TICKER, start=start_date, end=end_date, progress=False)

        # Handle multi-level columns from yfinance
        if isinstance(benchmark.columns, pd.MultiIndex):
            benchmark.columns = benchmark.columns.get_level_values(0)
        benchmark.columns = [str(col).lower() for col in benchmark.columns]

        market_data = pd.DataFrame(index=benchmark.index)
        market_data["benchmark_price"] = benchmark["close"]
        market_data["benchmark_returns"] = benchmark["close"].pct_change()

        # TODO: Add FRED API integration for actual risk-free rates
        # For now, use constant rate from config
        market_data["risk_free_rate"] = self.config.RISK_FREE_RATE / 252  # Daily rate

        # Save to cache
        market_data.to_parquet(cache_path)
        logger.info(f"Market data cached: {len(market_data)} records")

        return market_data

    def prepare_pilot_data(self) -> dict[str, Any]:
        """
        Prepare all data for pilot backtest (5 stocks, 5 years).

        Returns
        -------
        dict
            Dictionary with 'prices', 'financials', 'market_data'
        """
        logger.info("Preparing pilot backtest data...")

        prices = self.download_prices(
            self.config.PILOT_TICKERS, start_date=self.config.PILOT_START, end_date=self.config.PILOT_END
        )

        financials = self.download_financials(self.config.PILOT_TICKERS)

        market_data = self.get_market_data(start_date=self.config.PILOT_START, end_date=self.config.PILOT_END)

        logger.info("Pilot data preparation complete")

        return {"prices": prices, "financials": financials, "market_data": market_data}

    def prepare_full_data(self) -> dict[str, Any]:
        """
        Prepare all data for full backtest (50+ stocks, 15 years).

        Returns
        -------
        dict
            Dictionary with 'prices', 'financials', 'market_data'
        """
        logger.info("Preparing full backtest data...")

        prices = self.download_prices(
            self.config.FULL_TEST_TICKERS, start_date=self.config.START_DATE, end_date=self.config.END_DATE
        )

        financials = self.download_financials(self.config.FULL_TEST_TICKERS)

        market_data = self.get_market_data(start_date=self.config.START_DATE, end_date=self.config.END_DATE)

        logger.info("Full backtest data preparation complete")

        return {"prices": prices, "financials": financials, "market_data": market_data}
