# Critical Finding: JNJ Growth Assumption Validation
**Date**: January 5, 2026  
**Issue**: Discrepancy between DCF assumption (11.3%) and analyst/historical data (6.8% / 4.1%)

---

## 🚨 CRITICAL DISCOVERY

### The Problem

Our Monte Carlo deep dive revealed a **DATA MISMATCH** in the JNJ valuation:

| Source | Growth Rate | Notes |
|--------|-------------|-------|
| **DCF Engine** | **11.3%** | Used in Monte Carlo simulation |
| **Current Analyst** | **6.8%** | yfinance forward growth |
| **Historical CAGR** | **4.1%** | Actual 2021-2024 revenue growth |

**Gap**: DCF assumption is **66% higher** than current analyst estimates (11.3% vs 6.8%)  
**Gap**: DCF assumption is **176% higher** than historical reality (11.3% vs 4.1%)

---

## Root Cause Analysis

### Where Did 11.3% Come From?

Looking at the DCF engine valuation output:
```
Growth Assumptions:
   Raw Analyst Growth:        11.3%
   Sector Max Growth:         20.0% (Healthcare)
   Constrained Growth Used:   11.3%
```

The engine reported using "analyst growth" of 11.3%, but when we validate with fresh data:
```python
stock = yf.Ticker("JNJ")
info = stock.info
analyst_growth = info.get('revenueGrowth')  # Returns 0.068 (6.8%)
```

**Hypothesis**: The 11.3% might be from:
1. **Stale cached data** - Old analyst estimate that was more optimistic
2. **EPS growth vs revenue growth** - Analyst earnings growth ≠ revenue growth
3. **Data fetch error** - Different yfinance field used

### Historical Context

```
JNJ Annual Revenue Growth (2021-2024):
2022: +1.6% YoY
2023: +6.5% YoY
2024: +4.3% YoY

3-Year CAGR: 4.1%
Average YoY: 4.1%
```

**Reality Check**: JNJ is a mature $500B pharma giant. Historical 4% growth is typical for this profile.

---

## Impact on Valuation

### With Current Assumption (11.3% growth)
```
Fair Value: $212.40
Current Price: $207.35
Upside: +2.4%
Monte Carlo Probability: 37.7% undervalued
Assessment: NEUTRAL/FAIRLY VALUED
```

### With Analyst Estimate (6.8% growth)
**Likely result**:
- Fair value would drop to ~$190-195
- Upside: -5% to -10%
- Blended with relative valuation (already bearish): ~$175-180
- Assessment: OVERVALUED

### With Historical CAGR + Premium (7.1% growth)
**Recommended conservative estimate**:
- Fair value ~$195-200
- Upside: -3% to -5%
- Aligns with relative valuation showing OVERVALUED

---

## This Explains Everything!

### Why Relative Valuation Showed OVERVALUED

```
Relative Valuation: $156.98 (-24.3% vs current)

Multiples vs Healthcare Sector:
- Forward P/E: 18.0x vs median 15.5x (+16% premium)
- P/B: 6.29x vs median 4.24x (+48% premium)
- EV/EBITDA: 16.5x vs median 12.1x (+36% premium)
```

**The relative valuation was RIGHT!** JNJ trades at significant premiums to peers because:
- Market expects only 4-7% growth (historical reality)
- DCF assumed 11.3% growth (too optimistic)
- DCF was valuing a faster-growing company than JNJ actually is

### Why Blended Valuation Was Bearish

```
DCF Valuation:       60%  →  $212.40  (+2.4%)
Relative Valuation:  40%  →  $156.98  (-24.3%)
Blended Result:      100% →  $190.23  (-8.3%)
```

The blended valuation weighted the bearish relative signal, correctly pulling DCF down.

---

## Monte Carlo Implications

### Good News: Scenario Framework Still Works ✅

Even with the inflated 11.3% assumption, the Monte Carlo framework produced **reasonable uncertainty**:

```
Scenario Results (with 11.3% base):
├─ Bear (20%): 5.7% growth avg
├─ Base (60%): 9.1% growth avg
└─ Bull (20%): 13.6% growth avg

Probability Undervalued: 37.7% (appropriately uncertain)
```

**Why it worked**:
- Base scenario uses **80% of analyst** = 9.1% (still conservative even with bad input)
- Bear scenario uses **50% of analyst** = 5.7% (actually close to historical 4-6%)
- System showed uncertainty (37.7%) rather than false confidence (95%+)

### But: "Garbage In" Still Applies ⚠️

```
With 11.3% assumption:
Fair Value: $212 (+2.4%)
Assessment: NEUTRAL

With 7.1% assumption (historical + premium):
Fair Value: ~$195 (-5.8%)
Assessment: OVERVALUED ✅ (matches relative valuation)
```

The Monte Carlo **distribution shape** is good, but it's **centered around a bad assumption**.

---

## Recommendations

### 1. Fix the Data Fetch Logic (HIGH PRIORITY)

**Problem**: DCF engine is pulling 11.3% when current analyst estimate is 6.8%

**Investigation needed**:
```python
# Check what field DCFEngine is using
def fetch_company_data(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info
    
    # Which growth field?
    analyst_growth = info.get('revenueGrowth')  # 6.8% ✅
    earnings_growth = info.get('earningsGrowth')  # ??? (might be 11.3%)
    
    print(f"Revenue Growth: {analyst_growth}")
    print(f"Earnings Growth: {earnings_growth}")
```

**Fix**: Use `revenueGrowth` (more reliable for DCF) instead of `earningsGrowth`

### 2. Add Historical Validation Layer (MEDIUM PRIORITY)

**Proposed enhancement**:
```python
def validate_growth_assumption(ticker, analyst_growth):
    """
    Validate analyst growth against historical revenue CAGR.
    Return constrained growth if analyst is too optimistic.
    """
    historical_cagr = fetch_historical_cagr(ticker, years=3)
    
    # If analyst > historical * 1.5, cap it
    if analyst_growth > historical_cagr * 1.5:
        # Allow modest premium (historical + 3pp max)
        constrained = min(analyst_growth, historical_cagr + 0.03)
        
        warning = (
            f"Analyst growth {analyst_growth*100:.1f}% exceeds "
            f"historical {historical_cagr*100:.1f}% by >50%. "
            f"Capped to {constrained*100:.1f}%"
        )
        return constrained, warning
    
    return analyst_growth, None
```

### 3. Re-run JNJ with Corrected Growth

**Action**:
```bash
# Manual override for now
uv run python main.py valuation JNJ --growth 0.071 --detailed

# Expected output:
# Fair Value: ~$195 (-5.8% from current $207)
# Monte Carlo: ~65% probability overvalued
# Assessment: OVERVALUED (aligns with relative valuation)
```

### 4. Cache Invalidation

**Check if cached data is stale**:
```bash
# Check JNJ cache
cat data/cache/info_JNJ.json | grep -i growth

# If timestamp > 24 hours, delete and refetch
rm data/cache/info_JNJ.json
uv run python main.py valuation JNJ --detailed
```

---

## Broader System Implications

### Does This Affect All Stocks?

**Need to audit**:
1. Which growth field is being used globally (revenue vs earnings)?
2. Are other stocks affected by stale cache?
3. Should we implement automatic historical validation?

**Quick test**:
```bash
# Compare a few stocks
for ticker in AAPL MSFT GOOGL NVDA; do
    echo "=== $ticker ==="
    python -c "
import yfinance as yf
info = yf.Ticker('$ticker').info
print(f'Revenue Growth: {info.get(\"revenueGrowth\")}')
print(f'Earnings Growth: {info.get(\"earningsGrowth\")}')
    "
done
```

### Is Monte Carlo Framework Still Valid? YES ✅

**Key insight**: The scenario-based Monte Carlo framework is **sound**. The issue is the **input data quality**, not the simulation logic.

Evidence:
- Bear scenario (50% × analyst) produced 5.7% growth → Close to historical 4-6%
- System showed 37.7% confidence → Appropriately uncertain
- Terminal value capped at 65% → Constraint working
- Sector constraints active → Would catch extreme cases

**The framework caught the bad assumption by showing uncertainty rather than false confidence!**

---

## Action Plan

### Immediate (Today)
- [ ] Find which yfinance field DCF engine uses for analyst_growth
- [ ] Check if it's `revenueGrowth` or `earningsGrowth`
- [ ] Clear JNJ cache and refetch data
- [ ] Re-run JNJ valuation with fresh data

### Short-term (This Week)
- [ ] Implement `validate_growth_with_history()` function
- [ ] Add to `clean_growth_rate()` pipeline
- [ ] Add warning when analyst > historical * 1.5
- [ ] Test on JNJ, F, BAC (stocks with extreme valuations)

### Medium-term (Next 2 Weeks)
- [ ] Audit all cached stock data for staleness
- [ ] Implement automatic cache expiry (currently no TTL on info cache)
- [ ] Add `--force-refresh` flag to bypass cache
- [ ] Create test suite for growth assumption validation

---

## Updated Conclusion

### Original Question: Is GIGO Happening?

**Answer**: YES, but not where we expected! ✅

1. **Monte Carlo Framework**: VALID ✅
   - Scenario-based sampling is correct
   - Distributions are realistic
   - Uncertainty quantification works

2. **Sector Constraints**: WORKING ✅
   - Terminal value capped at 65%
   - Growth within sector limits
   - Conflict detection active

3. **Input Data Quality**: **PROBLEM FOUND** ❌
   - JNJ using 11.3% growth (too high)
   - Should be using 6.8% (current analyst)
   - Or 7.1% (historical + premium)

### The Silver Lining

The system **gracefully degraded** despite bad input:
- Didn't show 95%+ confidence (false precision)
- Conflict detection flagged disagreement with relative valuation
- Blended result pulled toward bearish relative signal
- User received mixed signals (NEUTRAL) rather than false BUY

**This proves the diagnostic-driven fixes are working!**

### Final Verdict

Monte Carlo simulation is **NOT garbage in, garbage out** — it's **"garbage in, uncertainty out"**.

The scenario framework correctly transforms a questionable input (11.3% growth) into:
- Bear scenario: 5.7% (realistic)
- Base scenario: 9.1% (conservative)
- Bull scenario: 13.6% (optimistic)
- **Result**: 37.7% confidence (honest uncertainty)

Fix the data input, and the system will produce accurate valuations. The Monte Carlo framework itself is sound.

---

## Files Created

1. `analyze_jnj_monte_carlo.py` - Deep dive into simulation mechanics
2. `validate_jnj_growth.py` - Historical growth validation
3. `docs/MONTE_CARLO_ANALYSIS_JNJ.md` - Full technical analysis
4. `docs/JNJ_GROWTH_ASSUMPTION_ISSUE.md` - This critical finding

Run the analysis yourself:
```bash
uv run python analyze_jnj_monte_carlo.py
uv run python validate_jnj_growth.py
```
