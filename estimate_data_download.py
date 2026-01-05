"""
Estimate time and data requirements for historical data download.

Analyzes:
1. What's already cached
2. Time estimates for full 50-stock download
3. Optimal timeframe recommendations
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.backtest.config import backtest_config
from src.external.xbrl_parser import XBRLDirectParser

# Test configuration
FULL_BACKTEST_TICKERS = backtest_config.FULL_TEST_TICKERS[:50]  # Top 50 S&P stocks
SAMPLE_TICKERS = ["AAPL", "MSFT", "JPM", "XOM", "WMT"]  # Representative sample


def check_cache_status():
    """Check what's already cached."""
    print("\n" + "=" * 80)
    print("XBRL CACHE STATUS")
    print("=" * 80)

    parser = XBRLDirectParser()

    # Check Company Facts JSON cache
    company_facts_files = list(parser.cache_dir.glob("CIK*.json"))
    ticker_mapping = parser.cache_dir / "ticker_cik_mapping.json"

    print(f"\nCompany Facts JSON files: {len(company_facts_files)}")
    if ticker_mapping.exists():
        print("✓ Ticker-to-CIK mapping cached")

    # Check processed financials cache
    financials_dir = Path("data/backtest/financials")
    if financials_dir.exists():
        xbrl_files = list(financials_dir.glob("*_xbrl.parquet"))
        print(f"Processed financial parquet files: {len(xbrl_files)}")

        if xbrl_files:
            print("\nCached tickers:")
            for f in sorted(xbrl_files)[:20]:  # Show first 20
                ticker = f.stem.replace("_annual_xbrl", "")
                print(f"  - {ticker}")
            if len(xbrl_files) > 20:
                print(f"  ... and {len(xbrl_files) - 20} more")

    # Calculate cache hit rate for full backtest
    cached_count = len(company_facts_files)
    total_needed = len(FULL_BACKTEST_TICKERS)
    cache_hit_rate = (cached_count / total_needed) * 100 if total_needed > 0 else 0

    print(f"\nCache hit rate for 50-stock backtest: {cached_count}/{total_needed} ({cache_hit_rate:.1f}%)")

    return cached_count, total_needed


def estimate_single_stock_time():
    """Estimate time to download one stock's data."""
    import time

    print("\n" + "=" * 80)
    print("SINGLE STOCK TIMING TEST")
    print("=" * 80)

    parser = XBRLDirectParser()

    # Test with one uncached stock (or clear cache for test)
    test_ticker = "GE"  # General Electric - lots of history
    print(f"\nTesting with {test_ticker}...")

    # Time cold fetch (with cache cleared)
    try:
        parser.clear_cache(test_ticker)
    except Exception:
        pass

    start = time.perf_counter()
    df = parser.get_financials(test_ticker, form_type="10-K")
    cold_time = time.perf_counter() - start

    # Time warm fetch (from cache)
    start = time.perf_counter()
    df2 = parser.get_financials(test_ticker, form_type="10-K")
    warm_time = time.perf_counter() - start

    print(f"\nResults for {test_ticker}:")
    print(f"  Data years: {len(df)} ({df.index.min().year}-{df.index.max().year})")
    print(f"  Metrics: {len(df.columns)}")
    print(f"  Cold fetch (API call): {cold_time:.3f}s")
    print(f"  Warm fetch (cache):    {warm_time:.3f}s")
    print(f"  Speedup: {cold_time/warm_time:.1f}x")

    return cold_time, warm_time, len(df)


def estimate_bulk_download_times(cold_time_per_stock: float, cached_count: int, total_needed: int):
    """Estimate time for full backtest data download."""
    print("\n" + "=" * 80)
    print("BULK DOWNLOAD TIME ESTIMATES")
    print("=" * 80)

    uncached_count = total_needed - cached_count
    sec_rate_limit = 0.1  # SEC allows 10 requests/second

    # Scenario 1: Sequential with rate limiting
    sequential_time = uncached_count * (cold_time_per_stock + sec_rate_limit)
    cached_time = cached_count * 0.04  # Fast cache reads

    # Scenario 2: Parallel (10 workers)
    parallel_cold = (uncached_count / 10) * (cold_time_per_stock + sec_rate_limit)

    # Scenario 3: All cached
    all_cached_time = total_needed * 0.04

    print(f"\nStocks to download: {total_needed}")
    print(f"Already cached: {cached_count} ({cached_count/total_needed*100:.1f}%)")
    print(f"Need to fetch: {uncached_count} ({uncached_count/total_needed*100:.1f}%)")

    print(f"\n📊 TIME ESTIMATES:")
    print(f"\nScenario 1: Sequential download (current implementation)")
    print(f"  Uncached stocks: {uncached_count} × {cold_time_per_stock:.2f}s = {uncached_count * cold_time_per_stock:.1f}s")
    print(f"  Rate limiting:   {uncached_count} × {sec_rate_limit}s = {uncached_count * sec_rate_limit:.1f}s")
    print(f"  Cached stocks:   {cached_count} × 0.04s = {cached_time:.1f}s")
    print(f"  TOTAL: {sequential_time + cached_time:.1f}s ({(sequential_time + cached_time)/60:.1f} minutes)")

    print(f"\nScenario 2: Parallel download (10 workers)")
    print(f"  Uncached (parallel): {parallel_cold:.1f}s")
    print(f"  Cached stocks:       {cached_time:.1f}s")
    print(f"  TOTAL: {parallel_cold + cached_time:.1f}s ({(parallel_cold + cached_time)/60:.1f} minutes)")

    print(f"\nScenario 3: All cached (after first run)")
    print(f"  All stocks from cache: {all_cached_time:.1f}s")

    return sequential_time + cached_time, parallel_cold + cached_time


def analyze_data_coverage():
    """Analyze available data years for sample stocks."""
    print("\n" + "=" * 80)
    print("HISTORICAL DATA COVERAGE ANALYSIS")
    print("=" * 80)

    parser = XBRLDirectParser()

    results = []
    for ticker in SAMPLE_TICKERS:
        try:
            df = parser.get_financials(ticker, form_type="10-K")
            if not df.empty:
                results.append(
                    {
                        "ticker": ticker,
                        "years": len(df),
                        "earliest": df.index.min().year,
                        "latest": df.index.max().year,
                        "span": df.index.max().year - df.index.min().year + 1,
                    }
                )
        except Exception as e:
            print(f"Warning: Failed to fetch {ticker}: {e}")

    if results:
        import pandas as pd

        df = pd.DataFrame(results)
        print(f"\nSample of {len(results)} stocks:")
        print(df.to_string(index=False))

        print(f"\n📈 SUMMARY:")
        print(f"  Average years: {df['years'].mean():.1f}")
        print(f"  Min years: {df['years'].min()}")
        print(f"  Max years: {df['years'].max()}")
        print(f"  Earliest year: {df['earliest'].min()}")
        print(f"  Latest year: {df['latest'].max()}")
        print(f"  Typical span: {df['span'].mean():.1f} years")

        return df["earliest"].min(), df["latest"].max(), df["years"].mean()

    return None, None, None


def recommend_optimal_timeframe(earliest_year: int, latest_year: int, avg_years: float):
    """Recommend optimal backtest timeframe."""
    print("\n" + "=" * 80)
    print("OPTIMAL TIMEFRAME RECOMMENDATIONS")
    print("=" * 80)

    available_span = latest_year - earliest_year
    current_year = 2026

    print(f"\n📅 AVAILABLE DATA:")
    print(f"  Earliest: {earliest_year}")
    print(f"  Latest:   {latest_year}")
    print(f"  Span:     {available_span} years")
    print(f"  Average per stock: {avg_years:.1f} years")

    print(f"\n🎯 TIMEFRAME OPTIONS:")

    # Option 1: 10 years (conservative)
    start_10y = current_year - 10
    print(f"\nOption 1: 10 years ({start_10y}-{latest_year})")
    print(f"  Pros: Fast execution, recent data, stable fundamentals")
    print(f"  Cons: Fewer cycles, may miss long-term trends")
    print(f"  Best for: Quick validation, recent-period focused strategies")

    # Option 2: 15 years (balanced)
    start_15y = current_year - 15
    print(f"\nOption 2: 15 years ({start_15y}-{latest_year})")
    print(f"  Pros: Includes 2008 crisis, multiple cycles, robust testing")
    print(f"  Cons: Some stocks may have limited early data")
    print(f"  Best for: Balanced backtest, stress-tested strategies")

    # Option 3: 20 years (comprehensive)
    start_20y = current_year - 20
    print(f"\nOption 3: 20 years ({start_20y}-{latest_year})")
    print(f"  Pros: Maximum history, includes dot-com bubble recovery")
    print(f"  Cons: Longer runtime, data may be sparse for newer companies")
    print(f"  Best for: Long-term strategies, comprehensive analysis")

    print(f"\n✅ RECOMMENDATION: 15 years ({start_15y}-{latest_year})")
    print(f"   Rationale:")
    print(f"   - Captures major market cycles (2008, 2020 COVID)")
    print(f"   - Most stocks have complete data")
    print(f"   - Balance between depth and execution speed")
    print(f"   - Industry standard for strategy backtesting")


def main():
    """Run all estimations."""
    print("\n" + "=" * 80)
    print("HISTORICAL DATA DOWNLOAD ESTIMATION")
    print("=" * 80)
    print(f"Target: {len(FULL_BACKTEST_TICKERS)} S&P 500 stocks")
    print(f"Sample: {len(SAMPLE_TICKERS)} representative stocks for timing")
    print("=" * 80)

    # 1. Check cache
    cached_count, total_needed = check_cache_status()

    # 2. Time single stock
    cold_time, warm_time, years = estimate_single_stock_time()

    # 3. Estimate bulk download
    sequential_time, parallel_time = estimate_bulk_download_times(cold_time, cached_count, total_needed)

    # 4. Analyze coverage
    earliest, latest, avg_years = analyze_data_coverage()

    # 5. Recommend timeframe
    if earliest and latest:
        recommend_optimal_timeframe(earliest, latest, avg_years)

    # Final summary
    print("\n" + "=" * 80)
    print("EXECUTIVE SUMMARY")
    print("=" * 80)
    print(f"\n📦 Current cache: {cached_count}/{total_needed} stocks ({cached_count/total_needed*100:.1f}%)")
    print(f"⏱️  Estimated download time (sequential): {sequential_time/60:.1f} minutes")
    print(f"⚡ Estimated download time (parallel):   {parallel_time/60:.1f} minutes")
    print(f"📊 Average data per stock: {avg_years:.1f} years")
    print(f"🎯 Recommended timeframe: 15 years (2011-2026)")
    print(
        f"\n💡 NEXT STEPS:\n"
        f"   1. Run full data download (~{sequential_time/60:.1f} min one-time cost)\n"
        f"   2. Configure backtest for 15-year period\n"
        f"   3. Execute backtest (data load will be fast after cache)\n"
    )
    print("=" * 80)


if __name__ == "__main__":
    import pandas as pd

    main()
