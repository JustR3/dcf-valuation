"""
Download full 20-year historical data for 50 S&P stocks.

Tests new Parquet caching system while building complete dataset.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tqdm import tqdm

from src.backtest.config import backtest_config
from src.external.xbrl_parser import XBRLDirectParser

# All 50 stocks
FULL_TICKERS = backtest_config.FULL_TEST_TICKERS[:50]


def download_all_data():
    """Download complete historical data for all 50 stocks."""
    print("\n" + "=" * 80)
    print("DOWNLOADING FULL 20-YEAR HISTORICAL DATA")
    print("=" * 80)
    print(f"Stocks: {len(FULL_TICKERS)}")
    print(f"Timeframe: Maximum available (2006-2025, ~20 years)")
    print(f"Form type: 10-K (annual filings)")
    print("=" * 80)

    parser = XBRLDirectParser()

    results = {}
    errors = []
    total_start = time.perf_counter()

    print(f"\n{'='*80}")
    print(f"PROGRESS")
    print(f"{'='*80}\n")

    for ticker in tqdm(FULL_TICKERS, desc="Downloading"):
        try:
            start = time.perf_counter()
            df = parser.get_financials(ticker, form_type="10-K")
            elapsed = time.perf_counter() - start

            if not df.empty:
                results[ticker] = {
                    "years": len(df),
                    "earliest": df.index.min().year,
                    "latest": df.index.max().year,
                    "metrics": len([c for c in df.columns if df[c].notna().any()]),
                    "time": elapsed,
                }
            else:
                errors.append((ticker, "No data returned"))

            # Small delay for SEC rate limiting
            time.sleep(0.1)

        except Exception as e:
            errors.append((ticker, str(e)))
            tqdm.write(f"❌ {ticker}: {str(e)[:50]}")

    total_time = time.perf_counter() - total_start

    # Summary
    print(f"\n{'='*80}")
    print("DOWNLOAD COMPLETE")
    print(f"{'='*80}")

    successful = len(results)
    failed = len(errors)

    print(f"\n📊 Results:")
    print(f"  Successful: {successful}/{len(FULL_TICKERS)} ({successful/len(FULL_TICKERS)*100:.1f}%)")
    print(f"  Failed: {failed}/{len(FULL_TICKERS)}")
    print(f"  Total time: {total_time:.1f}s ({total_time/60:.2f} minutes)")
    print(f"  Average time per stock: {total_time/len(FULL_TICKERS):.2f}s")

    if results:
        import pandas as pd

        df = pd.DataFrame.from_dict(results, orient="index")
        print(f"\n📈 Data Coverage:")
        print(f"  Average years: {df['years'].mean():.1f}")
        print(f"  Min years: {df['years'].min()}")
        print(f"  Max years: {df['years'].max()}")
        print(f"  Earliest year: {df['earliest'].min()}")
        print(f"  Latest year: {df['latest'].max()}")
        print(f"  Average metrics: {df['metrics'].mean():.1f}/9")

        # Cache analysis
        parquet_dir = Path("data/cache/xbrl_parquet")
        json_dir = Path("data/cache/company_facts")

        if parquet_dir.exists():
            parquet_files = list(parquet_dir.glob("*.parquet"))
            parquet_size = sum(f.stat().st_size for f in parquet_files) / 1024 / 1024
            print(f"\n💾 Cache Status:")
            print(f"  Parquet files: {len(parquet_files)}")
            print(f"  Parquet size: {parquet_size:.2f} MB")

        if json_dir.exists():
            json_files = list(json_dir.glob("CIK*.json"))
            json_size = sum(f.stat().st_size for f in json_files) / 1024 / 1024
            print(f"  JSON files: {len(json_files)}")
            print(f"  JSON size: {json_size:.1f} MB")

            if parquet_files:
                compression_ratio = json_size / parquet_size
                print(f"  Compression ratio: {compression_ratio:.0f}x")

        # Show top 10 by data coverage
        print(f"\n🏆 Top 10 by Historical Coverage:")
        top10 = df.nlargest(10, "years")[["years", "earliest", "latest", "metrics"]]
        for ticker, row in top10.iterrows():
            print(f"  {ticker}: {row['years']} years ({row['earliest']}-{row['latest']}) | {row['metrics']} metrics")

    if errors:
        print(f"\n❌ Errors ({len(errors)}):")
        for ticker, error in errors[:10]:  # Show first 10
            print(f"  {ticker}: {error[:70]}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")

    print(f"\n{'='*80}")
    print(f"✅ Dataset ready for 20-year backtest!")
    print(f"{'='*80}\n")

    return results, errors


if __name__ == "__main__":
    results, errors = download_all_data()
