"""
Parallel Workers Performance Test

Compares sequential vs parallel data fetching for DCF analysis.
Tests both company data fetching and historical price downloads.

Run with: uv run python test_parallel_performance.py
"""

import time
import src.env_loader
from src.dcf_engine import DCFEngine
from src.optimizer import PortfolioEngine

print("\n" + "="*80)
print("PARALLEL WORKERS PERFORMANCE TEST")
print("="*80 + "\n")

# Test stocks (mix of tech and other sectors)
test_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "INTC", "ORCL"]

print(f"Testing with {len(test_tickers)} stocks: {', '.join(test_tickers)}")
print()

# =============================================================================
# Test 1: Sequential Company Data Fetching (Current Method)
# =============================================================================

print("📊 TEST 1: Sequential Company Data Fetching")
print("-" * 80)
print("Method: Fetch stocks one-by-one with rate limiting")
print()

start_time = time.time()
results_sequential = {}
errors_sequential = []

for i, ticker in enumerate(test_tickers, 1):
    print(f"  [{i}/{len(test_tickers)}] Fetching {ticker}...", end="", flush=True)
    try:
        engine = DCFEngine(ticker, auto_fetch=True)
        if engine.is_ready:
            results_sequential[ticker] = engine.company_data
            print(" ✅")
        else:
            errors_sequential.append(ticker)
            print(f" ❌ {engine.last_error}")
    except Exception as e:
        errors_sequential.append(ticker)
        print(f" ❌ {e}")

sequential_time = time.time() - start_time
print()
print(f"⏱️  Time: {sequential_time:.2f} seconds")
print(f"✅ Successfully fetched: {len(results_sequential)}/{len(test_tickers)} stocks")
if errors_sequential:
    print(f"❌ Failed: {', '.join(errors_sequential)}")
print()

# =============================================================================
# Test 2: Parallel Company Data Fetching (New Method)
# =============================================================================

print("🚀 TEST 2: Parallel Company Data Fetching")
print("-" * 80)
print("Method: Fetch multiple stocks concurrently with ThreadPoolExecutor")
print()

start_time = time.time()
results_parallel = DCFEngine.fetch_batch_data(test_tickers, show_progress=True)
parallel_time = time.time() - start_time

success_count = sum(1 for v in results_parallel.values() if v is not None)
failed_tickers = [k for k, v in results_parallel.items() if v is None]

print()
print(f"⏱️  Time: {parallel_time:.2f} seconds")
print(f"✅ Successfully fetched: {success_count}/{len(test_tickers)} stocks")
if failed_tickers:
    print(f"❌ Failed: {', '.join(failed_tickers)}")
print()

# =============================================================================
# Test 3: Portfolio Historical Data (Sequential vs Parallel)
# =============================================================================

print("📈 TEST 3: Portfolio Historical Price Data")
print("-" * 80)

# Test with fewer stocks for price data (faster)
portfolio_tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]
print(f"Testing with {len(portfolio_tickers)} stocks: {', '.join(portfolio_tickers)}")
print()

# Sequential (old behavior - actually yfinance does this in one call anyway)
print("  Method A: Standard yfinance download...")
start_time = time.time()
engine_standard = PortfolioEngine(portfolio_tickers)
success_standard = engine_standard.fetch_data(period="1y")
standard_time = time.time() - start_time

if success_standard:
    print(f"  ⏱️  Time: {standard_time:.2f} seconds")
    print(f"  ✅ Fetched {len(engine_standard.prices)} days of data")
else:
    print(f"  ❌ Failed: {engine_standard._last_error}")
print()

# =============================================================================
# Performance Summary
# =============================================================================

print("="*80)
print("PERFORMANCE SUMMARY")
print("="*80)
print()

# Company data comparison
if parallel_time > 0:
    speedup = sequential_time / parallel_time
    time_saved = sequential_time - parallel_time
    pct_saved = (time_saved / sequential_time * 100) if sequential_time > 0 else 0
    
    print(f"📊 Company Data Fetching ({len(test_tickers)} stocks):")
    print(f"   Sequential:  {sequential_time:6.2f}s")
    print(f"   Parallel:    {parallel_time:6.2f}s")
    print(f"   Speedup:     {speedup:6.2f}x faster")
    print(f"   Time saved:  {time_saved:6.2f}s ({pct_saved:.1f}%)")
    print()

# Extrapolate to larger portfolios
if parallel_time > 0:
    print("📈 Projected Performance (Extrapolation):")
    
    for n_stocks in [20, 50, 100]:
        seq_est = (sequential_time / len(test_tickers)) * n_stocks
        par_est = (parallel_time / len(test_tickers)) * n_stocks
        saved = seq_est - par_est
        
        print(f"   {n_stocks:3d} stocks: {seq_est:6.1f}s → {par_est:6.1f}s  (save {saved:5.1f}s)")
    print()

# Performance recommendations
print("💡 Recommendations:")
print()

if speedup >= 3:
    print("   ✅ EXCELLENT: Parallel fetching provides significant speedup!")
    print("   → Use for all multi-stock operations")
    print("   → Especially beneficial for portfolio optimization (20+ stocks)")
elif speedup >= 2:
    print("   ✅ GOOD: Parallel fetching provides moderate speedup")
    print("   → Use for portfolio operations with 5+ stocks")
elif speedup >= 1.5:
    print("   ⚠️  MODEST: Parallel fetching provides minor speedup")
    print("   → Use for large portfolios only (20+ stocks)")
else:
    print("   ℹ️  MARGINAL: Parallel fetching may not be worth the complexity")
    print("   → Sequential fetching may be sufficient")

print()
print("="*80)
print("TEST COMPLETE")
print("="*80)
print()

# Usage tips
print("💡 Usage Tips:")
print()
print("1. For single stock analysis:")
print("   engine = DCFEngine('AAPL')")
print()
print("2. For multi-stock comparison (RECOMMENDED - PARALLEL):")
print("   results = DCFEngine.compare_stocks(['AAPL', 'MSFT', 'GOOGL'])")
print()
print("3. For manual parallel fetching:")
print("   data = DCFEngine.fetch_batch_data(['AAPL', 'MSFT', 'GOOGL'])")
print()
print("4. To disable parallel fetching (fallback to sequential):")
print("   results = DCFEngine.compare_stocks(tickers, use_parallel=False)")
print()
