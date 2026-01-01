# Dynamic WACC Integration: Risk-Free Rate & CAPE Adjustments

## Summary

Successfully integrated dynamic components into your DCF engine's WACC calculation:

1. **Dynamic 10-Year Treasury Yield** - Real-time risk-free rate (currently 4.16% vs static 4.5%)
2. **Shiller CAPE Market Valuation** - Macro adjustment based on market over/undervaluation
3. **Transparent Breakdown** - New `get_wacc_breakdown()` method shows all components

---

## Current Results (Jan 2026)

### Macro Environment
- **10Y Treasury**: 4.16% (dynamic, live data)
- **CAPE Ratio**: 33.0 (FAIR - between thresholds of 15 and 35)
- **WACC Adjustment**: 0 bps (fair market, no adjustment)

### Impact on Sample Stocks
| Ticker | Beta | Static WACC | Dynamic WACC | Difference |
|--------|------|-------------|--------------|------------|
| AAPL   | 1.11 | 12.25%      | 11.91%       | -34 bps    |
| NVDA   | 2.28 | 20.49%      | 20.15%       | -34 bps    |
| MSFT   | 1.07 | 11.99%      | 11.65%       | -34 bps    |

**Key Insight**: Current 10Y Treasury at 4.16% (vs 4.5% static) reduces WACC by 34 basis points across all stocks, making valuations slightly more generous.

---

## Architecture

### 1. Growth Rate Cleaning (`clean_growth_rate()`)

**Bayesian Prior Blending** - "Patient Prior" Process:

```
Case 1: Missing data → Use sector prior
Case 2: Extreme outlier (|g| > 100%) → Reject, use sector prior  
Case 3: Valid but extreme (-50% < g < -20% or 50% < g < 100%)
        → Blend: 70% analyst + 30% sector prior
Case 4: Reasonable (-20% < g < 50%) → Use analyst as-is
```

**Sector Priors** (from [config.py](config.py#L87-L99)):
- Technology: 15%
- Healthcare: 10%
- Consumer Cyclical: 8%
- Utilities: 3%

**Example**:
- Analyst predicts 60% growth (extreme)
- Tech sector prior: 15%
- Blended: `0.70 × 0.60 + 0.30 × 0.15 = 46.5%` ✓

---

### 2. WACC Calculation (`calculate_wacc()`)

**Formula**: `WACC = Risk-Free Rate + Beta × Market Risk Premium + CAPE Adjustment`

#### Components:

**A. Risk-Free Rate** ([regime.py](regime.py#L327-L355))
```python
get_10year_treasury_yield()
```
- Fetches live ^TNX (10-year Treasury yield index)
- Returns decimal (e.g., 0.0416 for 4.16%)
- Cached for 1 hour (volatile market data)
- Fallback: Config static rate (4.5%)

**B. Equity Risk Premium**
```python
Beta × Market_Risk_Premium
```
- Market Risk Premium: 7% (from config)
- Beta: Company-specific from yfinance

**C. CAPE Adjustment** ([regime.py](regime.py#L422-L459))
```python
calculate_cape_wacc_adjustment()
```

**Logic**:
- **CHEAP market** (CAPE < 15): Reduce WACC by up to -50 bps
  - Rationale: Undervalued market = lower risk premium justified
  - Formula: `-0.005 × (15 - CAPE) / 5`
  
- **EXPENSIVE market** (CAPE > 35): Increase WACC by up to +100 bps
  - Rationale: Overvalued market = higher risk premium
  - Formula: `+0.01 × (CAPE - 35) / 10`
  
- **FAIR market** (15 ≤ CAPE ≤ 35): No adjustment

**Current State**: CAPE = 33.0 → FAIR → 0 adjustment

---

### 3. Usage in DCF Engine

**Default Behavior** (both enabled):
```python
wacc = engine.calculate_wacc()
# Uses dynamic Treasury + CAPE adjustment
```

**Disable Features**:
```python
# Static rate only
wacc = engine.calculate_wacc(use_dynamic_rf=False, use_cape_adjustment=False)

# Dynamic rate, no CAPE
wacc = engine.calculate_wacc(use_cape_adjustment=False)
```

**Get Detailed Breakdown**:
```python
breakdown = engine.get_wacc_breakdown()
# Returns dict with all components, sources, and contributions
```

---

## Implementation Details

### Files Modified

1. **[src/regime.py](src/regime.py)** (NEW FUNCTIONS)
   - `get_10year_treasury_yield()` - Fetch live Treasury yield
   - `get_current_cape()` - Fetch CAPE ratio estimate
   - `calculate_cape_wacc_adjustment()` - Calculate WACC adjustment
   - `get_dynamic_risk_free_rate()` - Wrapper with source info
   - `CapeData` dataclass - Container for CAPE data

2. **[src/dcf_engine.py](src/dcf_engine.py#L209-L240)** (UPDATED)
   - `calculate_wacc()` - Enhanced with dynamic RF and CAPE
   - `get_wacc_breakdown()` - New transparency method

3. **[test_dynamic_wacc.py](test_dynamic_wacc.py)** (NEW)
   - Demonstration script showing all features

---

## CAPE Data Source

**Current Implementation**: 
- Fetches SPY ETF trailing PE ratio
- Multiplies by 1.2x to approximate CAPE (which uses 10-year smoothed earnings)
- Historical CAPE mean: ~16-17

**Note**: True Shiller CAPE requires 10-year inflation-adjusted earnings from:
- http://www.econ.yale.edu/~shiller/data.htm
- Current implementation is a reasonable real-time proxy

---

## Configuration ([config.py](config.py#L35-L41))

```python
# Macro God: Shiller CAPE Configuration
ENABLE_MACRO_ADJUSTMENT: bool = True
CAPE_LOW_THRESHOLD: float = 15.0   # Cheap market
CAPE_HIGH_THRESHOLD: float = 35.0  # Expensive market
CAPE_SCALAR_LOW: float = 1.2       # Not currently used (reserved for return adjustments)
CAPE_SCALAR_HIGH: float = 0.7      # Not currently used
CAPE_CACHE_HOURS: int = 168        # 1 week cache
```

Adjustments are linear interpolations between thresholds.

---

## Example Output

```
═══ WACC Analysis: AAPL ═══

📊 Risk-Free Rate (10Y Treasury)
Source: 10Y Treasury: 4.16%
Rate: 4.16%

🌍 Shiller CAPE Macro Adjustment
CAPE Ratio: 33.0
Market State: FAIR
WACC Adjustment: +0 bps

WACC Components Breakdown
┌────────────────────────────┬─────────────┬──────────────┐
│ Component                  │       Value │ Contribution │
├────────────────────────────┼─────────────┼──────────────┤
│ Risk-Free Rate             │       4.16% │        4.16% │
│ Beta × Market Risk Premium │ 1.11 × 7.0% │        7.75% │
│ CAPE Adjustment            │      +0 bps │       +0.00% │
│ ───────────────            │ ─────────── │  ─────────── │
│ Base WACC                  │      11.91% │              │
│ Final WACC                 │      11.91% │              │
└────────────────────────────┴─────────────┴──────────────┘

Static WACC (config): 12.25%
Difference: -34 bps
```

---

## Benefits

1. **Market-Aware Valuation**: WACC adjusts with current interest rate environment
2. **Macro Context**: CAPE adjustment accounts for overall market valuation
3. **Transparency**: Full breakdown shows where discount rate comes from
4. **Backward Compatible**: Can disable features to use static rates
5. **Cached Efficiently**: Treasury (1 hour), CAPE (1 week) to avoid API spam

---

## Next Steps

### Optional Enhancements:

1. **True CAPE Data**: Integrate Shiller's actual CAPE dataset
   - Scrape from http://www.econ.yale.edu/~shiller/data.htm
   - More accurate than PE proxy

2. **Regime-Based Adjustments**: Use your existing `RegimeDetector`
   - RISK_OFF → Increase WACC (flight to quality)
   - RISK_ON → Decrease WACC (risk appetite)

3. **Volatility Adjustment**: Add VIX-based risk premium
   - High VIX → Higher WACC
   - Low VIX → Lower WACC

4. **Credit Spread**: Corporate vs Treasury spread
   - BBB-Treasury spread as additional risk factor

---

## Testing

Run the test script:
```bash
python test_dynamic_wacc.py
```

Use in your DCF workflow:
```python
from src.dcf_engine import DCFEngine

engine = DCFEngine("AAPL")
result = engine.get_intrinsic_value()
# Automatically uses dynamic WACC

# Or get breakdown
breakdown = engine.get_wacc_breakdown()
print(f"Current 10Y Treasury: {breakdown['risk_free_rate']*100:.2f}%")
print(f"CAPE: {breakdown['cape_info']['cape_ratio']:.1f}")
print(f"Final WACC: {breakdown['final_wacc']*100:.2f}%")
```
