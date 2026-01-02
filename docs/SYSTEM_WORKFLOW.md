# DCF Valuation System Workflow

## High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER ENTRY POINT                                 │
│                          dcf.py (CLI)                                     │
│                                                                           │
│  Options: Interactive Mode | Direct Command | Multiple Tickers           │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     COMMAND ROUTER (src/cli/)                            │
│                                                                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │  Valuation      │  │   Portfolio     │  │   Compare       │        │
│  │  Command        │  │   Command       │  │   Command       │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
│          │                     │                     │                   │
└──────────┼─────────────────────┼─────────────────────┼──────────────────┘
           │                     │                     │
           ▼                     ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        CORE ENGINE LAYER                                 │
│                                                                           │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    DCFEngine (src/dcf_engine.py)                  │  │
│  │                                                                    │  │
│  │  Main Methods:                                                     │  │
│  │  • fetch_data()          - Collect company data                   │  │
│  │  • calculate_dcf()       - Core DCF valuation                     │  │
│  │  • calculate_wacc()      - Weighted Average Cost of Capital       │  │
│  │  • run_scenario_analysis() - Bull/Base/Bear scenarios             │  │
│  │  • run_sensitivity_analysis() - Parameter sensitivity             │  │
│  │  • run_stress_test()     - Macro stress testing                   │  │
│  │  • reverse_dcf()         - Implied growth from price              │  │
│  │  • calculate_ev_sales_valuation() - Pre-profit companies          │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                             │                                             │
└─────────────────────────────┼─────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     DATA SOURCES & CACHING                               │
│                                                                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │  yfinance API   │  │  Damodaran NYU  │  │    FRED API     │        │
│  │  (Company Data) │  │  (Sector Priors)│  │  (Macro Data)   │        │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘        │
│           │                     │                     │                   │
│           │                     │                     │                   │
│  ┌────────▼─────────────────────▼─────────────────────▼────────┐       │
│  │              DataCache (src/utils.py)                         │       │
│  │                                                                │       │
│  │  Location: data/cache/                                        │       │
│  │  • Ticker info: JSON (24 hours)                               │       │
│  │  • Cash flows: Parquet (24 hours)                             │       │
│  │  • Historical prices: Parquet (24 hours)                      │       │
│  │                                                                │       │
│  │  DamodaranLoader Internal Cache (src/external/damodaran.py)  │       │
│  │  • In-memory: 30 days                                         │       │
│  │  • Beta datasets (XLS)                                         │       │
│  │  • Margin datasets (XLS)                                       │       │
│  │                                                                │       │
│  │  FREDConnector Cache (src/external/fred.py)                   │       │
│  │  • In-memory: 24 hours                                         │       │
│  │  • 10Y Treasury yield                                          │       │
│  │  • Shiller CAPE ratio                                          │       │
│  └────────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     ADVANCED FEATURES LAYER                              │
│                                                                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │ RegimeDetector  │  │   Portfolio     │  │   Monte Carlo   │        │
│  │ (regime.py)     │  │   Optimizer     │  │   Simulation    │        │
│  │                 │  │   (portfolio.py)│  │   (display.py)  │        │
│  │ • SPY 200-SMA   │  │ • Black-Litt.   │  │ • Probability   │        │
│  │ • VIX Term Str. │  │ • Efficient Fr. │  │ • Confidence    │        │
│  │ • Risk On/Off   │  │ • DCF-Views     │  │   Intervals     │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          OUTPUT LAYER                                    │
│                     (src/cli/display.py)                                 │
│                                                                           │
│  • Rich formatted terminal output                                        │
│  • Tables, panels, progress bars                                         │
│  • CSV export functionality                                              │
│  • Conviction ratings (HIGH/MODERATE/SPECULATIVE/HOLD/PASS)             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Process Flow

### 1. **Entry Point: CLI Initialization** (`dcf.py`)

**What it does:**
- Parses command-line arguments
- Loads environment variables (API keys)
- Routes to appropriate command handler

**Available Options:**
- **Interactive Mode** (default): `uv run dcf.py`
- **Valuation**: `uv run dcf.py valuation AAPL`
  - Flags: `--scenarios`, `--sensitivity`, `--stress`, `--detailed`
- **Portfolio**: `uv run dcf.py portfolio AAPL MSFT GOOGL`
  - Flags: `--method` (min_volatility, max_sharpe, efficient_risk)
- **Compare**: `uv run dcf.py compare AAPL MSFT GOOGL`

**Next Step:** Routes to command handler in `src/cli/commands.py`

---

### 2. **Command Processing** (`src/cli/commands.py`)

**What it does:**
- Validates tickers and parameters
- Creates DCFEngine instances
- Orchestrates analysis types

**Available Options:**

#### A. **Single Stock Valuation**
```python
handle_valuation_command(args)
```
- **Standard DCF**: Basic valuation with fair value calculation
- **Scenario Analysis** (`--scenarios`): Bull/Base/Bear scenarios
- **Sensitivity Analysis** (`--sensitivity`): Growth vs WACC grid
- **Stress Test** (`--stress`): Macro regime-based stress testing
- **Detailed Mode** (`--detailed`): Technical breakdown with cash flows

#### B. **Multi-Stock Comparison**
```python
handle_compare_command(args)
```
- Side-by-side valuation of multiple stocks
- Automatic ranking by upside potential
- Conviction-based filtering

#### C. **Portfolio Optimization**
```python
handle_portfolio_command(args)
```
- Black-Litterman optimization with DCF views
- Methods: `min_volatility`, `max_sharpe`, `efficient_risk`
- Conviction-weighted allocations

**Next Step:** Calls DCFEngine methods

---

### 3. **Core Engine: Data Fetching** (`DCFEngine.fetch_data()`)

**What it does:**
- Fetches company data from yfinance
- Applies caching to avoid rate limits
- Validates data quality

**Data Sources (in order):**

1. **yfinance API** → `DataCache` (24-hour cache)
   - Company info (JSON): `data/cache/info_{TICKER}.json`
   - Cash flows (Parquet): `data/cache/cashflow_{TICKER}.parquet`
   - Historical prices (Parquet): `data/cache/prices_*.parquet`

2. **Damodaran NYU** → In-memory cache (30-day cache)
   - Sector betas: `https://pages.stern.nyu.edu/~adamodar/pc/datasets/betas.xls`
   - Operating margins: `https://pages.stern.nyu.edu/~adamodar/pc/datasets/margin.xls`
   - **Cache Status:** ✅ **IMPLEMENTED** (in-memory, 30-day expiry)

3. **FRED API** → In-memory cache (24-hour cache)
   - 10-Year Treasury Yield: `DGS10`
   - Shiller CAPE Ratio: Custom calculation
   - **Cache Status:** ✅ **IMPLEMENTED** (in-memory, 24-hour expiry)

**Collected Data:**
- Free Cash Flow (FCF) - TTM annualized
- Shares outstanding
- Current price & market cap
- Beta (company-specific or Damodaran sector beta)
- Analyst growth estimates
- Revenue & sector classification

**Data Validation:**
- Minimum FCF threshold
- Beta reasonableness (0.01 - 5.0)
- Growth rate sanity checks (-50% to 100%)

**Next Step:** Proceeds to valuation calculations

---

### 4. **Core Engine: WACC Calculation** (`DCFEngine.calculate_wacc()`)

**What it does:**
- Calculates Weighted Average Cost of Capital using CAPM
- Applies dynamic risk-free rate and CAPE adjustments

**Formula:**
```
WACC = Risk-Free Rate + Beta × Market Risk Premium

With adjustments:
- Dynamic RF: Live 10Y Treasury from FRED
- CAPE Adjustment: +/- 1% based on market valuation
```

**Available Options:**
- `use_dynamic_rf=True`: Live FRED data (recommended)
- `use_dynamic_rf=False`: Static config rate (4.5%)
- `use_cape_adjustment=True`: Shiller CAPE macro adjustment
- `use_cape_adjustment=False`: No macro adjustment

**Default Configuration** (`src/config.py`):
- Static Risk-Free Rate: 4.5%
- Market Risk Premium: 5.5%
- CAPE Cheap Threshold: < 20
- CAPE Expensive Threshold: > 30

**Next Step:** Used in DCF valuation

---

### 5. **Core Engine: DCF Valuation** (`DCFEngine.calculate_dcf()`)

**What it does:**
- Projects future cash flows
- Calculates terminal value
- Discounts to present value

**Process:**

1. **Growth Rate Determination:**
   - **Option A:** User-provided growth rate
   - **Option B:** Bayesian blend of analyst estimates + Damodaran sector priors
     - Default: 70% analyst + 30% sector prior (configurable in `config.py`)
   - **Option C:** Sector prior only (if no analyst data)

2. **Explicit Forecast Period:**
   ```
   For t = 1 to N years:
     FCF[t] = FCF[0] × (1 + growth)^t
     PV[t] = FCF[t] / (1 + WACC)^t
   ```

3. **Terminal Value:**
   
   **Option A: Gordon Growth** (mature companies)
   ```
   Terminal Value = FCF[N] × (1 + term_growth) / (WACC - term_growth)
   ```
   - Best for: Utilities, Consumer Defensive, mature tech
   - Assumes perpetual stable growth (typically 2-3%)

   **Option B: Exit Multiple** (growth companies)
   ```
   Terminal Value = FCF[N] × Exit_Multiple
   ```
   - Best for: Technology, Healthcare, high-growth sectors
   - Uses sector-average EV/Sales multiples from Damodaran

4. **Enterprise Value:**
   ```
   EV = Sum(PV[t]) + Terminal_PV
   Value per Share = EV / Shares Outstanding
   ```

**Output:**
- Fair value per share
- Upside/downside % vs current price
- Cash flow projections
- Terminal value breakdown
- Conviction rating (HIGH/MODERATE/SPECULATIVE/HOLD/PASS)

**Next Step:** Display results or run additional analysis

---

### 6. **Advanced Analysis Options**

#### A. **Scenario Analysis** (`DCFEngine.run_scenario_analysis()`)

**What it does:**
- Runs three scenarios: Bull, Base, Bear
- Varies growth rates and WACC

**Default Ranges:**
- **Bull:** Growth +50%, WACC -20%
- **Base:** User inputs
- **Bear:** Growth -50%, WACC +20%

**Output:** Valuation range with probabilities

---

#### B. **Sensitivity Analysis** (`DCFEngine.run_sensitivity_analysis()`)

**What it does:**
- Creates a grid of Growth × WACC combinations
- Shows how valuation changes with assumptions

**Default Grid:**
- Growth: ±40% around base (5 steps)
- WACC: ±30% around base (5 steps)
- Total: 25 scenarios

**Output:** Heatmap-style table

---

#### C. **Stress Test** (`DCFEngine.run_stress_test()`)

**What it does:**
- Tests valuation under macro regime shifts
- Uses RegimeDetector for market conditions

**Regimes:**
1. **RISK_ON**: Lower WACC (optimistic)
2. **RISK_OFF**: Higher WACC (defensive)
3. **CAUTION**: Mixed conditions

**Adjustments:**
- WACC: ±1-2% based on regime
- Growth: Company-specific adjustments
- Multiple compression in RISK_OFF

**Output:** Valuation under each regime

---

#### D. **Reverse DCF** (`DCFEngine.reverse_dcf()`)

**What it does:**
- Solves for implied growth rate given current price
- Answers: "What growth does the market expect?"

**Method:**
- Uses root-finding algorithm (Brent's method)
- Finds growth rate where DCF value = market price

**Output:**
- Implied growth rate
- Comparison to analyst estimates
- Assessment (REASONABLE, AGGRESSIVE, SPECULATIVE, etc.)

---

#### E. **EV/Sales Valuation** (`DCFEngine.calculate_ev_sales_valuation()`)

**What it does:**
- Alternative valuation for pre-profit companies
- Uses sector-average EV/Sales multiples

**Process:**
1. Get company revenue
2. Fetch sector EV/Sales multiple from Damodaran or peers
3. Calculate: `EV = Revenue × Multiple`

**Best for:** Startups, growth companies with negative FCF (e.g., RIVN, PLTR pre-profit)

---

### 7. **Portfolio Optimization** (`src/portfolio.py`)

**What it does:**
- Optimizes portfolio weights using Black-Litterman model
- Integrates DCF valuations as investor "views"

**Process:**

1. **View Construction:**
   - DCF upside % → Expected return view
   - Conviction level → View confidence weight
   - Monte Carlo probability → Additional weighting

2. **Conviction Filtering:**
   - **HIGH CONVICTION:** Full weight (30% + MC bonus)
   - **MODERATE:** Reduced weight (20% + MC bonus)
   - **SPECULATIVE:** Heavily discounted (10% + MC bonus)
   - **HOLD/PASS:** Excluded entirely

3. **Optimization Methods:**
   - `max_sharpe`: Maximum Sharpe ratio
   - `min_volatility`: Minimum portfolio variance
   - `efficient_risk`: Target risk level

**Output:**
- Optimal weights for each stock
- Expected return, volatility, Sharpe ratio
- Allocation percentages

---

### 8. **Market Regime Detection** (`src/regime.py`)

**What it does:**
- Detects current market regime for risk adjustment
- Used in stress testing and dynamic WACC

**Signals:**

1. **SPY 200-Day SMA:**
   - RISK_ON: Price > SMA
   - RISK_OFF: Price < SMA

2. **VIX Term Structure:**
   - Backwardation (VIX9D > VIX): Fear → RISK_OFF
   - Contango (VIX9D < VIX < VIX3M): Calm → RISK_ON

**Combined Assessment:**
- Both bullish → RISK_ON
- Both bearish → RISK_OFF
- Mixed → CAUTION

**Usage:**
- Adjusts WACC in stress tests
- Informs portfolio risk tolerance
- Provides macro context for valuations

---

### 9. **Output & Display** (`src/cli/display.py`)

**What it does:**
- Formats results using Rich library
- Provides color-coded conviction ratings
- Exports to CSV if requested

**Features:**
- **Tables:** Comparison tables, cash flow projections
- **Panels:** Highlighted key metrics
- **Progress bars:** Multi-stock processing
- **Color coding:**
  - 🟢 GREEN: Undervalued (>20% upside)
  - 🟡 YELLOW: Fairly valued (±20%)
  - 🔴 RED: Overvalued (>20% downside)

**Export:**
- CSV export with `--export` flag
- Includes all valuation metrics

---

## Configuration & Customization

### Global Configuration (`src/config.py`)

**Economic Parameters:**
- `RISK_FREE_RATE`: 4.5% (static fallback)
- `MARKET_RISK_PREMIUM`: 5.5%

**Validation Thresholds:**
- `MIN_GROWTH_RATE`: -50%
- `MAX_GROWTH_RATE`: 100%

**Bayesian Blending:**
- `BAYESIAN_ANALYST_WEIGHT`: 0.7 (70% analyst, 30% sector prior)

**Sector Priors:** (fallback if Damodaran unavailable)
```python
SECTOR_GROWTH_PRIORS = {
    "Technology": 0.12,
    "Healthcare": 0.08,
    "Financial Services": 0.06,
    # ... etc
}
```

**CAPE Adjustment:**
- `CAPE_CHEAP_THRESHOLD`: < 20 → -1% WACC adjustment
- `CAPE_EXPENSIVE_THRESHOLD`: > 30 → +1% WACC adjustment

---

## Data Flow Summary

```
User Input (Ticker)
    ↓
CLI Parser (dcf.py)
    ↓
Command Handler (cli/commands.py)
    ↓
DCFEngine.fetch_data()
    ├→ yfinance API → DataCache (24h) → Company Data
    ├→ Damodaran NYU → In-memory (30d) → Sector Priors
    └→ FRED API → In-memory (24h) → Macro Data
    ↓
DCFEngine.calculate_wacc()
    ├→ CAPM formula
    └→ Dynamic adjustments (FRED, CAPE)
    ↓
DCFEngine.calculate_dcf()
    ├→ Project cash flows
    ├→ Calculate terminal value
    └→ Discount to present
    ↓
Optional Analysis
    ├→ Scenario Analysis
    ├→ Sensitivity Analysis
    ├→ Stress Test
    ├→ Reverse DCF
    └→ Portfolio Optimization
    ↓
Display Results (cli/display.py)
    ├→ Rich formatted output
    └→ CSV export (optional)
```

---

## Key Takeaways

1. **Caching is Comprehensive:**
   - ✅ yfinance data: 24-hour file cache
   - ✅ Damodaran data: 30-day in-memory cache
   - ✅ FRED data: 24-hour in-memory cache

2. **Three-Tier Data Strategy:**
   - **Live Data:** Company-specific metrics (yfinance)
   - **Sector Priors:** Academic benchmarks (Damodaran)
   - **Macro Context:** Economic indicators (FRED)

3. **Flexible Valuation:**
   - DCF for profitable companies
   - EV/Sales for pre-profit companies
   - Multiple terminal value methods

4. **Risk Management:**
   - Regime-based adjustments
   - Conviction-based portfolio filtering
   - Monte Carlo probability weighting

5. **User Experience:**
   - Interactive mode for exploration
   - Direct commands for automation
   - Rich visual output
   - CSV export for further analysis
