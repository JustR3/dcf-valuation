# SEC EDGAR Parser Implementation Roadmap

**Date:** January 5, 2026  
**Status:** ✅ FEASIBLE - Proceeding with Option B  
**Estimated Cost:** $2-10 (GPT-4o-mini)  
**Estimated Time:** 2-3 days implementation + 5 hours data parsing

## Feasibility Analysis Results

### ✅ Data Availability Confirmed
- **SEC EDGAR API:** Free, unlimited, official source
- **Historical Coverage:** 10-15+ years for major stocks
- **XBRL Company Facts:** Aggregated financial data ready to use
- **Sample Data:**
  - AAPL: 11 years of financials (FY2009-2024)
  - MSFT: 15 years of revenue data (FY2010-2025)
  - TSLA: 114 annual entries available

### 💰 Cost Analysis
**Full Backtest (50 stocks × 15 years = 750 filings):**
- GPT-4o-mini: **$2.36** (recommended)
- GPT-4o: $39.38 (higher quality, not necessary)
- SEC API: **$0** (free forever)

**One-time cost** - results cached permanently

### ⏱️ Time Estimate
- Parsing: ~25 seconds per filing = **5.2 hours total**
- Run overnight, use forever
- Incremental: Only parse new filings quarterly

## Implementation Plan

### Phase 1: Setup & Dependencies (30 minutes)
```bash
# Install dependencies
pip install instructor openai

# Set environment variable
export OPENAI_API_KEY="sk-..."

# Test API connection
python -c "from openai import OpenAI; print(OpenAI().models.list())"
```

### Phase 2: Adapt Virattt's Code (4-6 hours)

**File:** `src/external/sec_edgar_parser.py`

**Key Components:**
1. **SECFilingDownloader** - Get 10-K filings for ticker + year
2. **XBRLDataExtractor** - Parse XBRL using GPT-4
3. **FinancialStatementModels** - Pydantic models for DCF
4. **CacheManager** - Store parsed data per filing

**Code Structure:**
```python
from pydantic import BaseModel, Field
import instructor
from openai import OpenAI

# Define DCF-specific financial data
class DCFFinancials(BaseModel):
    """Financial data required for DCF valuation."""
    fiscal_year: int
    period_end_date: str
    
    # Income Statement
    revenue: float = Field(description="Total revenue")
    operating_income: float = Field(description="Operating income")
    net_income: float = Field(description="Net income")
    
    # Cash Flow Statement
    operating_cash_flow: float = Field(description="Cash from operations")
    capex: float = Field(description="Capital expenditures")
    free_cash_flow: float = Field(description="Free cash flow (OCF - CapEx)")
    
    # Balance Sheet
    total_debt: float = Field(description="Total debt (long-term + short-term)")
    cash: float = Field(description="Cash and cash equivalents")
    total_assets: float = Field(description="Total assets")
    stockholders_equity: float = Field(description="Total equity")
    
    # Share Information
    shares_outstanding: float = Field(description="Common shares outstanding")

class SECEDGARParser:
    def __init__(self, openai_api_key: str, cache_dir: Path):
        self.client = instructor.from_openai(
            OpenAI(api_key=openai_api_key),
            mode=instructor.Mode.JSON
        )
        self.cache_dir = cache_dir
    
    def get_financials(self, ticker: str, fiscal_year: int) -> DCFFinancials:
        """Extract DCF-relevant financials from 10-K filing."""
        # 1. Get CIK from ticker
        cik = self._get_cik(ticker)
        
        # 2. Find 10-K filing for fiscal year
        accession_number = self._get_10k_accession(cik, fiscal_year)
        
        # 3. Download XBRL data
        xbrl_url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/Revenues.json"
        # ... download filing content
        
        # 4. Parse with GPT-4
        result = self.client.chat.completions.create(
            model="gpt-4o-mini",
            response_model=DCFFinancials,
            messages=[
                {"role": "system", "content": "Extract DCF financial metrics from 10-K filing."},
                {"role": "user", "content": filing_text}
            ]
        )
        
        # 5. Cache result
        self._cache_result(ticker, fiscal_year, result)
        
        return result
```

### Phase 3: Integration with Backtest (2-3 hours)

**Modify:** `src/backtest/data_loader.py`

**Changes:**
```python
from src.external.sec_edgar_parser import SECEDGARParser

class HistoricalDataLoader:
    def __init__(self, config):
        self.config = config
        # Add SEC parser
        self.sec_parser = SECEDGARParser(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            cache_dir=config.FINANCIALS_DIR
        )
    
    def download_financials(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        """Download historical quarterly financials using SEC EDGAR."""
        results = {}
        
        for ticker in tqdm(tickers, desc="Parsing SEC filings"):
            # Check cache first
            cached = self._load_cached_sec_data(ticker)
            if cached is not None:
                results[ticker] = cached
                continue
            
            # Parse 10-K filings for last 15 years
            financials = []
            for year in range(2010, 2026):
                try:
                    data = self.sec_parser.get_financials(ticker, year)
                    financials.append(data.model_dump())
                except Exception as e:
                    logger.warning(f"Failed to parse {ticker} FY{year}: {e}")
            
            # Convert to DataFrame
            df = pd.DataFrame(financials)
            df['date'] = pd.to_datetime(df['period_end_date'])
            df = df.set_index('date').sort_index()
            
            results[ticker] = df
            
        return results
```

### Phase 4: Testing (2 hours)

**Test Script:** `tests/test_sec_integration.py`

```python
def test_parse_aapl_2023():
    """Test parsing AAPL FY2023 10-K."""
    parser = SECEDGARParser(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        cache_dir=Path("data/sec_cache")
    )
    
    result = parser.get_financials("AAPL", 2023)
    
    # Validate results
    assert result.fiscal_year == 2023
    assert result.revenue > 380_000_000_000  # Apple ~$383B in FY2023
    assert result.free_cash_flow > 90_000_000_000  # ~$99B FCF
    assert result.shares_outstanding > 15_000_000_000  # ~15.5B shares
    
def test_parse_pilot_stocks():
    """Test parsing all 5 pilot stocks for 2023."""
    parser = SECEDGARParser(...)
    
    for ticker in ["AAPL", "JPM", "XOM", "WMT", "JNJ"]:
        result = parser.get_financials(ticker, 2023)
        assert result.revenue > 0
        assert result.free_cash_flow != 0  # Can be negative
        print(f"{ticker}: Revenue=${result.revenue:,.0f}, FCF=${result.free_cash_flow:,.0f}")
```

### Phase 5: Full Backtest Run (5-6 hours)

**Execution:**
```bash
# 1. Set API key
export OPENAI_API_KEY="sk-..."

# 2. Run pilot (5 stocks, 3 years) first
python run_pilot_backtest.py --use-sec-edgar --years 3

# Expected: ~75 filings × 25 sec = 30 minutes, cost ~$0.20

# 3. If pilot succeeds, run full backtest
python run_full_backtest.py --use-sec-edgar

# Expected: 750 filings × 25 sec = 5 hours, cost ~$2.50
```

## Alternative: Use XBRL Company Facts Directly

**Faster approach** - Skip GPT-4, use raw XBRL API:

```python
def get_financials_from_xbrl_api(self, ticker: str) -> pd.DataFrame:
    """Get financials directly from SEC Company Facts API (no GPT-4)."""
    cik = self._get_cik(ticker)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    
    response = requests.get(url, headers={"User-Agent": SEC_USER_AGENT})
    data = response.json()
    
    # Extract US-GAAP metrics
    us_gaap = data["facts"]["us-gaap"]
    
    # Build DataFrame from XBRL facts
    metrics = {
        "revenue": "Revenues",
        "net_income": "NetIncomeLoss",
        "fcf": "NetCashProvidedByUsedInOperatingActivitiesC ontinuingOperations",
        # ... map XBRL tags to our fields
    }
    
    # Parse each metric's time series
    # This is FREE (no GPT-4 cost) but requires XBRL tag knowledge
```

**Pros:**
- $0 cost (free SEC data, no AI)
- Faster (no API calls)
- More deterministic

**Cons:**
- XBRL tags are inconsistent across companies
- Requires mapping each company's specific tags
- Missing data needs manual handling

**Recommendation:** Try XBRL-only first, fall back to GPT-4 for edge cases.

## Risk Mitigation

### Issue 1: GPT-4 Parsing Errors
**Solution:** Validate outputs with assertions
```python
if result.revenue <= 0:
    raise ValueError(f"Invalid revenue: {result.revenue}")
if result.shares_outstanding <= 0:
    raise ValueError(f"Invalid shares: {result.shares_outstanding}")
```

### Issue 2: Rate Limiting
**Solution:** Add delays and retry logic
```python
import time
from tenacity import retry, wait_exponential

@retry(wait=wait_exponential(min=1, max=60))
def call_gpt4_with_retry(self, filing_text):
    time.sleep(0.5)  # Rate limit: 2 requests/sec
    return self.client.chat.completions.create(...)
```

### Issue 3: Inconsistent XBRL Tags
**Solution:** GPT-4 handles this naturally - it understands context
```python
# GPT-4 can find "Total Revenue" even if tagged as:
# - Revenues
# - RevenueFromContractWithCustomerExcludingAssessedTax
# - SalesRevenueNet
# No manual mapping needed!
```

### Issue 4: Missing Quarters
**Solution:** Skip missing data, interpolate if needed
```python
if fiscal_year not in available_years:
    logger.warning(f"No 10-K for {ticker} FY{fiscal_year}")
    return None  # Backtest handles missing data gracefully
```

## Success Criteria

### Phase 2 Complete When:
- ✅ Can parse 1 ticker × 1 year successfully
- ✅ Output validates (positive revenue, reasonable FCF)
- ✅ Cached to parquet for reuse
- ✅ Unit tests pass

### Phase 3 Complete When:
- ✅ Backtest uses SEC data instead of yfinance
- ✅ Pilot run (5 stocks × 3 years) completes
- ✅ Forward returns calculated correctly
- ✅ Performance metrics generated

### Phase 5 Complete When:
- ✅ Full backtest (50 stocks × 15 years) completes
- ✅ All data cached (no re-parsing needed)
- ✅ Results match or exceed commercial API quality
- ✅ Total cost < $5

## Timeline

| Phase | Task | Duration | Blocker? |
|-------|------|----------|----------|
| 1 | Setup dependencies | 30 min | Yes (need API key) |
| 2 | Adapt virattt's code | 4-6 hours | Yes (core implementation) |
| 3 | Integrate with backtest | 2-3 hours | No (can parallelize) |
| 4 | Test pilot stocks | 2 hours | Yes (validate approach) |
| 5 | Full backtest run | 5-6 hours | No (overnight) |

**Critical Path:** Phases 1 → 2 → 4 → 5  
**Total Time:** ~2 days active work + 1 overnight run

## Decision: GO WITH OPTION B ✅

**Rationale:**
1. ✅ **Proven Technology:** Virattt's notebook demonstrates working implementation
2. ✅ **Low Cost:** $2-10 vs $30-200/month for commercial APIs
3. ✅ **Free Data:** SEC EDGAR is official, unlimited, permanent
4. ✅ **Manageable Complexity:** ~200-300 lines of code
5. ✅ **Enables 15-Year Backtest:** Full historical validation possible

**vs Option A (Commercial API):**
- Commercial: $360-2400/year ongoing cost
- SEC: $2-10 one-time cost
- Winner: **SEC EDGAR (Option B)**

**vs Option C (Forward Test Only):**
- Forward test: 1-2 years to validate
- Historical backtest: Results immediately
- Winner: **SEC EDGAR (Option B)**

## Next Steps

1. **Immediate:** Get OpenAI API key ($10-20 credit)
2. **Day 1:** Implement SEC parser (Phases 1-2)
3. **Day 2:** Test on pilot stocks (Phase 4)
4. **Day 3:** Run full backtest overnight (Phase 5)

---

**Ready to proceed!** SEC EDGAR parser is the optimal solution for historical backtesting.
