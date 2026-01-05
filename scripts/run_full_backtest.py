#!/usr/bin/env python3
"""
Run Full 20-Year Backtest
==========================

Execute comprehensive backtest on 48 stocks over 20 years (2006-2026).

This validates:
- DCF model performance over multiple market cycles
- Strategy robustness through 2008 crisis and 2020 COVID crash
- Long-term predictive power of fundamental valuation
- Performance across different market regimes

Usage:
    python run_full_backtest.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.backtest import (
    BacktestAnalyzer,
    BacktestResults,
    PerformanceMetrics,
    WalkForwardBacktest,
    backtest_config,
)
from src.logging_config import get_logger

logger = get_logger(__name__)


def save_results(results: BacktestResults, metrics: PerformanceMetrics, output_dir: Path):
    """Save backtest results and metrics to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Convert to DataFrame and save signals
    df = results.to_dataframe()
    signals_file = output_dir / f"full_backtest_{timestamp}.csv"
    df.to_csv(signals_file, index=False)
    logger.info(f"Saved signals to {signals_file}")

    # Save metrics
    metrics_file = output_dir / f"full_metrics_{timestamp}.json"
    with open(metrics_file, "w") as f:
        json.dump(metrics.to_dict(), f, indent=2, default=str)
    logger.info(f"Saved metrics to {metrics_file}")

    return signals_file, metrics_file


def print_summary(results: BacktestResults, metrics: PerformanceMetrics, analyzer: BacktestAnalyzer):
    """Print executive summary of backtest results."""
    print("\n" + "=" * 80)
    print("FULL 20-YEAR BACKTEST RESULTS")
    print("=" * 80)

    print(f"\n📊 BACKTEST CONFIGURATION")
    print(f"  Period: {results.start_date.strftime('%Y-%m-%d')} to {results.end_date.strftime('%Y-%m-%d')}")
    print(f"  Duration: {(results.end_date - results.start_date).days / 365.25:.1f} years")
    print(f"  Stocks: {len(results.tickers)}")
    print(f"  Rebalances: {results.num_rebalances}")
    print(f"  Total Signals: {len(results.signals):,}")

    # Use analyzer's built-in metrics display
    analyzer.print_metrics(metrics)


def main():
    """Run full 20-year backtest."""
    print("\n" + "=" * 80)
    print("FULL 20-YEAR BACKTEST EXECUTION")
    print("=" * 80)

    print(f"\nTickers: {', '.join(backtest_config.FULL_TEST_TICKERS[:10])}, ...")
    print(f"Period:  {backtest_config.START_DATE.strftime('%Y-%m-%d')} to {backtest_config.END_DATE.strftime('%Y-%m-%d')}")
    print(f"Rebalance: Annual")

    print("\n" + "=" * 80 + "\n")

    logger.info("Starting full 20-year backtest...")

    # Initialize backtest engine
    engine = WalkForwardBacktest(backtest_config)

    # Run full backtest (uses configured START_DATE, END_DATE, and FULL_TEST_TICKERS)
    results = engine.run_full()

    if results is None or not results.signals:
        logger.error("Backtest failed - no results generated")
        print("\n❌ Backtest failed to generate results")
        return

    # Analyze results
    analyzer = BacktestAnalyzer(backtest_config)
    metrics = analyzer.analyze(results)

    # Save results
    output_dir = backtest_config.RESULTS_DIR
    signals_file, metrics_file = save_results(results, metrics, output_dir)

    # Print summary
    print_summary(results, metrics, analyzer)

    # Additional insights
    print("\n💡 INSIGHTS")
    print(f"  Results saved to:")
    print(f"    Signals: {signals_file}")
    print(f"    Metrics: {metrics_file}")
    print(f"\n  Next steps:")
    print(f"    1. Review IC and win rates to assess predictive power")
    print(f"    2. Analyze quintile spreads for stock selection ability")
    print(f"    3. Examine performance across different market regimes")
    print(f"    4. Compare vs SPY benchmark")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
