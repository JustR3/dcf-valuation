#!/usr/bin/env python3
"""
Run Pilot Backtest
==================

Execute pilot backtest on 5 stocks over 5 years (2019-2024).

This validates:
- Walk-forward methodology works correctly
- Point-in-time data reconstruction is accurate
- Performance metrics calculation is robust
- Results are interpretable and actionable

Usage:
    python run_pilot_backtest.py
"""

import json
from datetime import datetime
from pathlib import Path

from src.backtest import BacktestAnalyzer, WalkForwardBacktest, backtest_config
from src.logging_config import get_logger

logger = get_logger(__name__)


def save_results(results, metrics, output_dir: Path):
    """Save backtest results and metrics to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save signals to CSV
    df = results.to_dataframe()
    csv_path = output_dir / f"pilot_backtest_{datetime.now():%Y%m%d_%H%M%S}.csv"
    df.to_csv(csv_path, index=False)
    logger.info(f"Saved signals to {csv_path}")
    
    # Save metrics to JSON
    metrics_dict = metrics.to_dict()
    metrics_dict['metadata'] = {
        'start_date': results.start_date.isoformat(),
        'end_date': results.end_date.isoformat(),
        'num_rebalances': results.num_rebalances,
        'tickers': results.tickers,
        'num_signals': len(results.signals),
    }
    
    json_path = output_dir / f"pilot_metrics_{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(json_path, 'w') as f:
        json.dump(metrics_dict, f, indent=2)
    logger.info(f"Saved metrics to {json_path}")


def main():
    """Run pilot backtest and display results."""
    print("\n" + "="*80)
    print("PILOT BACKTEST EXECUTION")
    print("="*80)
    print(f"\nTickers: {', '.join(backtest_config.PILOT_TICKERS)}")
    print(f"Period:  {backtest_config.PILOT_START.date()} to {backtest_config.PILOT_END.date()}")
    print(f"Rebalance: Quarterly")
    print("\n" + "="*80 + "\n")
    
    # Initialize backtest engine
    engine = WalkForwardBacktest()
    
    # Run backtest
    logger.info("Starting pilot backtest...")
    results = engine.run_pilot()
    
    # Analyze results
    analyzer = BacktestAnalyzer()
    metrics = analyzer.analyze(results)
    
    # Display metrics
    analyzer.print_metrics(metrics)
    
    # Save results
    output_dir = Path("data/backtest/results")
    save_results(results, metrics, output_dir)
    
    # Summary statistics
    print("\n📊 SUMMARY STATISTICS")
    print("="*80)
    df = results.to_dataframe()
    
    print("\nSignal Upside Distribution:")
    print(df['upside_pct'].describe())
    
    print("\n1-Year Forward Returns Distribution:")
    print((df['actual_1y'] * 100).describe())
    
    print("\nSignals by Ticker:")
    print(df.groupby('ticker')['signal'].value_counts().unstack(fill_value=0))
    
    print("\nAverage Returns by Signal (1Y):")
    signal_returns = df.groupby('signal')['actual_1y'].mean() * 100
    for signal, return_val in signal_returns.items():
        print(f"  {signal.upper():5s}: {return_val:+.1f}%")
    
    print("\n" + "="*80)
    print("✅ PILOT BACKTEST COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
