
## Project Overview
A comprehensive Discounted Cash Flow (DCF) valuation tool for fundamental stock analysis and portfolio optimization. This toolkit implements sophisticated DCF valuation with Monte Carlo simulation, market regime detection, and Black-Litterman portfolio optimization. Built for fundamental analysts and value investors who need rigorous cash flow analysis combined with quantitative portfolio construction.

## Development Environment Setup

### Required Tools
- Python 3.12+
- `uv` for dependency management (exclusively - no pip/poetry)
- Pre-commit hooks (enforced via `.pre-commit-config.yaml`)
- Git for version control

### Initial Setup
```bash
# Install dependencies
uv sync

# Install pre-commit hooks (REQUIRED)
uv run pre-commit install

# Verify setup
uv run pre-commit run --all-files
```

## Code Style & Standards

### Python Conventions
Follow PEP 8 style guide with these specific rules:

**Line Length & Formatting**
- 120 characters maximum (configured in `pyproject.toml`)
- Use Ruff for both linting AND formatting (replaces Black + isort)
- Run `uv run ruff format .` before committing

**Type Hints (REQUIRED)**
```python
from __future__ import annotations  # Enable forward references

from decimal import Decimal
from pathlib import Path

# Prefer modern syntax (Python 3.12+)
def calculate_wacc(
    equity_weight: float,
    debt_weight: float,
    cost_equity: float,
    cost_debt: float,
    tax_rate: float
) -> Decimal:
    """Calculate WACC with precise decimal arithmetic."""
    ...

# Use union syntax instead of Optional
def get_beta(ticker: str) -> float | None:
    ...

# Type complex structures
def process_portfolio(
    holdings: dict[str, float],
    weights: list[float]
) -> tuple[float, float]:
    ...
```

**Naming Conventions**
```python
# Constants (module-level, after imports)
RISK_FREE_RATE = 0.045
MAX_ITERATIONS = 10_000

# Functions and variables
def calculate_terminal_value(fcf: float, growth_rate: float) -> float:
    discount_rate = 0.10
    ...

# Classes
class DCFEngine:
    def __init__(self) -> None:
        self._cache: dict[str, float] = {}  # Private attributes

# Private functions
def _validate_growth_rate(rate: float) -> None:
    """Private helper - not part of public API."""
    ...
```

**Import Organization**
```python
# Standard library (alphabetical)
import logging
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Third-party packages (alphabetical)
import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

# Local application imports (alphabetical)
from src.config import Config
from src.dcf_engine import DCFEngine
from src.exceptions import ValidationError
```

**Code Quality Rules**
- Maximum function length: 50 lines (extract helpers if longer)
- Maximum cyclomatic complexity: 10 (simplify if higher)
- Use `pathlib.Path`, never `os.path`
- No bare `except:` - always specify exception types
- No nested list comprehensions beyond 2 levels
- Prefer explicit over implicit: clear variable names, no magic numbers
- Use context managers for all file/resource operations

**String Formatting**
```python
# Use f-strings exclusively
ticker = "AAPL"
value = 150.25
print(f"DCF for {ticker}: ${value:.2f}")

# For complex formatting
report = f"""
DCF Valuation Report
Ticker: {ticker}
Fair Value: ${value:,.2f}
Date: {datetime.now():%Y-%m-%d}
"""
```

### Linting & Formatting Workflow

**Pre-commit Hooks (Enforced)**
All code must pass these checks before commit:
- `ruff check` - Linting (E, F, I, N, W, UP rules)
- `ruff format` - Auto-formatting
- `mypy` - Static type checking
- Trailing whitespace removal
- End-of-file fixer

**Manual Commands**
```bash
# Format code
uv run ruff format .

# Check linting
uv run ruff check . --fix

# Type checking
uv run mypy src/

# Run all checks
uv run pre-commit run --all-files
```

**Ruff Configuration** (in `pyproject.toml`)
```toml
[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]
ignore = ["E501"]  # Line length handled by formatter
```

### Documentation Standards

**NumPy-Style Docstrings (REQUIRED for public functions)**
```python
def calculate_wacc(
    equity_weight: float,
    debt_weight: float,
    cost_equity: float,
    cost_debt: float,
    tax_rate: float
) -> Decimal:
    """
    Calculate Weighted Average Cost of Capital (WACC) with tax shield.

    The WACC represents the average rate a company pays to finance its assets,
    weighted by the proportion of equity and debt in its capital structure.

    Parameters
    ----------
    equity_weight : float
        Proportion of equity financing, range [0, 1]
    debt_weight : float
        Proportion of debt financing, range [0, 1]
    cost_equity : float
        Cost of equity as decimal (e.g., 0.10 for 10%)
    cost_debt : float
        Pre-tax cost of debt as decimal
    tax_rate : float
        Corporate tax rate as decimal (e.g., 0.21 for 21%)

    Returns
    -------
    Decimal
        WACC as high-precision decimal

    Raises
    ------
    ValueError
        If weights don't sum to 1.0 ± 0.001
        If any rate is negative
        If tax_rate > 1.0

    Notes
    -----
    Formula:
    .. math::
        WACC = \\frac{E}{V} \\times R_e + \\frac{D}{V} \\times R_d \\times (1 - T_c)

    Where:
    - E/V = equity weight
    - D/V = debt weight
    - Re = cost of equity
    - Rd = cost of debt
    - Tc = corporate tax rate

    The tax shield applies only to debt interest expense.

    References
    ----------
    .. [1] Damodaran, A. (2012). Investment Valuation, 3rd Ed., Chapter 8.
    .. [2] Brealey, R. A., Myers, S. C., & Allen, F. (2020). Principles of
           Corporate Finance, 13th Ed., Chapter 17.

    Examples
    --------
    >>> calculate_wacc(0.6, 0.4, 0.12, 0.06, 0.21)
    Decimal('0.091040')
    """
    if not np.isclose(equity_weight + debt_weight, 1.0, atol=0.001):
        raise ValueError(f"Weights must sum to 1.0, got {equity_weight + debt_weight:.4f}")
    ...
```

**Inline Comments**
```python
# Use comments for WHY, not WHAT
# Good
fcf = revenue * fcf_margin  # Apply margin to avoid recalculating cash flows

# Bad
fcf = revenue * fcf_margin  # Calculate free cash flow

# Complex formulas need explanation
# Terminal value using Gordon Growth Model
# Assumes perpetual growth at risk-free rate
terminal_value = fcf_final * (1 + growth) / (wacc - growth)
```

## Commit Guidelines

### Commit Message Format (Conventional Commits)

**Structure**
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Rules**
- **Subject**: Imperative mood, no period, max 50 chars
- **Body**: Wrap at 72 chars, explain WHAT and WHY (not HOW)
- **Footer**: Breaking changes, issue references

**Types**
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `refactor:` - Code change that neither fixes bug nor adds feature
- `test:` - Adding or updating tests
- `perf:` - Performance improvement
- `build:` - Build system or dependency changes
- `ci:` - CI/CD configuration changes
- `style:` - Formatting changes (not code style fixes)

**Scopes** (optional but recommended)
- `dcf` - DCF engine calculations
- `portfolio` - Portfolio optimization
- `monte-carlo` - Monte Carlo simulations
- `api` - External API integrations
- `cli` - Command-line interface
- `config` - Configuration management

**Examples**
```
feat(dcf): add WACC calculation with tax shield adjustment

Implement WACC calculation supporting debt tax shields per Damodaran
methodology. Uses Decimal type for precise monetary calculations.

Includes validation for weight constraints and negative rate handling.

Closes #42
```

```
fix(monte-carlo): correct terminal value distribution sampling

Previously used normal distribution for terminal growth rates, causing
unrealistic negative values. Now using truncated normal distribution
bounded at [0%, 15%] as per Damodaran's recommendations.

Fixes #128
```

```
test: add property-based tests for DCF calculations

Add hypothesis-based tests ensuring WACC monotonicity with respect to
cost of equity and debt. Tests verify mathematical properties hold
across 10,000 random valid inputs.
```

```
perf(portfolio): vectorize covariance matrix calculations

Replace iterative correlation calculations with NumPy vectorized
operations. Reduces runtime from O(n²) to O(n) for n assets.

Benchmark: 500 assets now process in 0.3s vs 12.4s previously.
```

```
BREAKING CHANGE: modify DCF output structure

DCF results now return dataclass instead of dict for type safety.
Migration required in all callers.

Before: result["fair_value"]
After: result.fair_value
```

### Atomic Commit Rules

**DO Commit When:**
1. **Complete unit of work**: Single function/class fully implemented AND tested
2. **Bug fix isolated**: Fix addresses one specific issue, passes tests
3. **Tests pass**: All existing + new tests pass locally
4. **Linting passes**: Pre-commit hooks pass without errors
5. **Documentation complete**: New code has docstrings, README updated if needed

**Specific Thresholds:**
- New function + tests + docstring = 1 commit
- Multiple related tests for same module = 1 commit
- 3+ typo/formatting fixes in same file = 1 commit
- Configuration file with all related changes = 1 commit

**DO NOT Commit:**
- Work-in-progress code (use `git stash` instead)
- Code that breaks any existing test
- Commented-out code blocks (delete or explain in PR if needed temporarily)
- Only whitespace/formatting changes unless explicitly refactoring formatting
- Debug print statements or temporary test code

**Commit Granularity**
```bash
# Good: Atomic, focused commits
git commit -m "feat(dcf): add terminal value calculation"
git commit -m "test: add terminal value edge case tests"
git commit -m "docs: document terminal value assumptions"

# Bad: Bundled unrelated changes
git commit -m "add DCF stuff and fix bugs"  # Too vague, multiple concerns

# Bad: Too granular
git commit -m "add function signature"
git commit -m "add function body"
git commit -m "add docstring"  # Should be 1 commit
```

### Branch Naming
```bash
# Format: <type>/<short-description>
feat/add-wacc-calculation
fix/terminal-value-validation
refactor/vectorize-cash-flows
test/add-dcf-regression-tests
docs/update-api-reference
```

## Testing Requirements

### Test Structure & Organization

**Directory Layout**
```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_dcf_engine.py
│   ├── test_portfolio.py
│   └── test_regime.py
├── integration/
│   ├── test_external_apis.py
│   └── test_end_to_end_dcf.py
├── performance/
│   ├── test_monte_carlo_speed.py
│   └── test_portfolio_optimization.py
├── property/
│   └── test_dcf_properties.py  # hypothesis tests
└── fixtures/
    ├── sample_financials.json
    └── benchmark_valuations.xlsx
```

**Fixture Organization** (`conftest.py`)
```python
import pytest
import pandas as pd
from decimal import Decimal

@pytest.fixture(scope="session")
def sample_financial_data() -> dict[str, pd.DataFrame]:
    """Load reusable financial statements for testing."""
    return {
        "income_stmt": pd.read_json("tests/fixtures/sample_financials.json"),
        "balance_sheet": pd.read_csv("tests/fixtures/balance_sheet.csv"),
        "cash_flow": pd.read_csv("tests/fixtures/cash_flow.csv")
    }

@pytest.fixture(scope="function")
def dcf_engine():
    """Fresh DCF engine instance per test."""
    from src.dcf_engine import DCFEngine
    return DCFEngine()

@pytest.fixture
def mock_yfinance_data(monkeypatch):
    """Mock yfinance API calls."""
    def mock_download(*args, **kwargs):
        return pd.DataFrame({"Close": [150.0, 151.0, 149.5]})
    monkeypatch.setattr("yfinance.download", mock_download)
```

### Test Categories

**1. Unit Tests** (`tests/unit/`)
```python
def test_calculate_wacc_with_valid_inputs(dcf_engine):
    """Test WACC calculation with standard capital structure."""
    result = dcf_engine.calculate_wacc(
        equity_weight=0.6,
        debt_weight=0.4,
        cost_equity=0.12,
        cost_debt=0.06,
        tax_rate=0.21
    )
    expected = Decimal("0.091040")
    assert result == pytest.approx(expected, abs=1e-5)

def test_wacc_raises_on_invalid_weights():
    """Test WACC validation rejects weights not summing to 1.0."""
    with pytest.raises(ValueError, match="Weights must sum to 1.0"):
        calculate_wacc(0.6, 0.5, 0.12, 0.06, 0.21)
```

**2. Property-Based Tests** (`tests/property/`)
```python
from hypothesis import given, strategies as st

@given(
    equity_weight=st.floats(min_value=0.01, max_value=0.99),
    cost_equity=st.floats(min_value=0.05, max_value=0.25),
    cost_debt=st.floats(min_value=0.01, max_value=0.15),
    tax_rate=st.floats(min_value=0.0, max_value=0.5)
)
def test_wacc_monotonicity(equity_weight, cost_equity, cost_debt, tax_rate):
    """WACC should increase with cost of equity, all else equal."""
    debt_weight = 1 - equity_weight
    
    wacc1 = calculate_wacc(equity_weight, debt_weight, cost_equity, cost_debt, tax_rate)
    wacc2 = calculate_wacc(equity_weight, debt_weight, cost_equity + 0.01, cost_debt, tax_rate)
    
    assert wacc2 > wacc1, "WACC must increase with cost of equity"
```

**3. Regression Tests** (compare to known valuations)
```python
def test_jnj_dcf_matches_benchmark():
    """Verify JNJ valuation matches Excel DCF model (±2%)."""
    result = dcf_engine.calculate_dcf("JNJ", years=5)
    benchmark = 165.42  # From validated Excel model
    
    assert result.fair_value == pytest.approx(benchmark, rel=0.02)
```

**4. Integration Tests** (`tests/integration/`)
```python
def test_full_dcf_workflow_with_real_api(mock_yfinance_data):
    """Test complete DCF calculation with mocked external APIs."""
    result = run_dcf_analysis(
        ticker="AAPL",
        projection_years=5,
        use_external_data=True
    )
    
    assert result.fair_value > 0
    assert result.wacc > 0
    assert len(result.projected_fcf) == 5
```

**5. Performance Tests** (`tests/performance/`)
```python
import time

def test_monte_carlo_performance():
    """Monte Carlo with 10k iterations must complete in <5 seconds."""
    start = time.perf_counter()
    
    result = run_monte_carlo_simulation(
        ticker="AAPL",
        iterations=10_000,
        years=5
    )
    
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"Monte Carlo too slow: {elapsed:.2f}s"
```

### Test Naming & Documentation

**Function Names**
```python
# Pattern: test_<function>_<scenario>_<expected_result>
def test_calculate_dcf_with_negative_growth_raises_error():
    """DCF calculation should reject negative terminal growth rates."""
    ...

def test_portfolio_optimization_with_three_assets_converges():
    """Black-Litterman optimization should converge for 3-asset portfolio."""
    ...
```

**Test Docstrings**
```python
def test_wacc_calculation_with_no_debt():
    """
    Test WACC calculation for 100% equity-financed company.
    
    Scenario:
        Company has no debt (debt_weight = 0)
    
    Expected:
        WACC should equal cost of equity exactly
    
    Financial Rationale:
        With zero debt, there's no tax shield benefit, so WACC simplifies
        to cost of equity. This tests the edge case of pure equity financing.
    """
    ...
```

### Coverage Requirements

**Targets**
- Overall: >85% line coverage
- Critical modules (DCF engine, WACC, terminal value): >95%
- Utility functions: >75%
- CLI interfaces: >60% (interaction logic)

**Run Coverage**
```bash
# Generate coverage report
uv run pytest --cov=src --cov-report=html --cov-report=term

# View HTML report
open htmlcov/index.html

# Fail if coverage below threshold
uv run pytest --cov=src --cov-fail-under=85
```

**Financial Test Validation**
```python
# Use appropriate tolerance for float comparisons
import numpy as np

# For monetary values (dollars)
assert result == pytest.approx(expected, abs=0.01)  # ±$0.01

# For percentages/rates
assert rate == pytest.approx(expected_rate, abs=1e-4)  # ±0.01%

# For ratios/multiples
assert ratio == pytest.approx(expected_ratio, rel=0.01)  # ±1%

# NumPy arrays
np.testing.assert_allclose(result_array, expected_array, rtol=1e-5)
```

### Test Execution

**Run Tests Locally**
```bash
# All tests
uv run pytest

# Specific test file
uv run pytest tests/unit/test_dcf_engine.py

# Specific test function
uv run pytest tests/unit/test_dcf_engine.py::test_calculate_wacc

# With verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x

# Run only fast tests (skip slow integration tests)
uv run pytest -m "not slow"
```

## Logging Standards

### Log Levels

**When to Use Each Level**
```python
import logging

logger = logging.getLogger(__name__)

# DEBUG: Detailed diagnostic info for development
logger.debug(f"WACC calculation inputs: equity={equity_weight}, debt={debt_weight}")

# INFO: Confirmation that things work as expected
logger.info(f"Successfully calculated DCF for {ticker}: ${fair_value:.2f}")

# WARNING: Something unexpected but handled
logger.warning(f"Beta calculation failed for {ticker}, using industry average: {default_beta}")

# ERROR: Error that prevented operation but didn't crash
logger.error(f"Failed to fetch data for {ticker}: {error_msg}")

# CRITICAL: Serious error, application may not continue
logger.critical(f"Database connection lost, cannot proceed with analysis")
```

### Logging Financial Calculations

**Structured Logging**
```python
# Log key financial metrics with context
logger.info(
    f"DCF Complete | ticker={ticker} | "
    f"fair_value=${fair_value:.2f} | wacc={wacc:.4f} | "
    f"terminal_growth={terminal_growth:.4f} | years={years}"
)

# Log calculation steps for debugging
logger.debug(f"Step 1/5: Free cash flow projection complete - fcf={fcf}")
logger.debug(f"Step 2/5: WACC calculated - value={wacc:.6f}")
logger.debug(f"Step 3/5: Terminal value - value=${terminal_value:,.2f}")
```

**Do NOT Log Sensitive Data**
```python
# NEVER log API keys, tokens, credentials
# BAD
logger.debug(f"Using API key: {api_key}")

# GOOD
logger.debug(f"API key loaded: {'*' * 8}{api_key[-4:]}")

# NEVER log full financial data structures (may contain PII)
# BAD
logger.info(f"Processing financials: {financial_data}")

# GOOD
logger.info(f"Processing financials for ticker={ticker}, rows={len(financial_data)}")
```

## Module Organization

### File Structure Rules

**Maximum Sizes**
- File: 500 lines (excluding docstrings)
- Function: 50 lines
- Class: 300 lines
- If exceeded, split into multiple modules

**Module Purpose**
```
src/
├── __init__.py              # Package exports
├── config.py                # Configuration management
├── constants.py             # All constants (rates, thresholds)
├── exceptions.py            # Custom exception classes
├── dcf_engine.py            # Core DCF calculations
├── portfolio.py             # Portfolio optimization
├── regime.py                # Market regime detection
├── utils.py                 # Generic utilities (date parsing, etc.)
├── validation.py            # Input validation functions
└── external/
    ├── __init__.py
    ├── yfinance_client.py   # Yahoo Finance API wrapper
    ├── fred_client.py       # FRED API wrapper
    └── damodaran_client.py  # Damodaran data scraper
```

**Constants Location** (`src/constants.py`)
```python
"""Financial constants and default values."""

# Market data defaults
DEFAULT_RISK_FREE_RATE = 0.045
DEFAULT_MARKET_RETURN = 0.10
DEFAULT_TAX_RATE = 0.21

# Calculation parameters
MAX_PROJECTION_YEARS = 10
MIN_PROJECTION_YEARS = 3
TERMINAL_GROWTH_MAX = 0.05

# Monte Carlo settings
DEFAULT_MONTE_CARLO_ITERATIONS = 10_000
CONFIDENCE_INTERVAL = 0.95

# Validation thresholds
MAX_GROWTH_RATE = 0.50  # 50% max annual growth
MIN_DISCOUNT_RATE = 0.01  # 1% minimum
```

**When to Split Modules**
```python
# If dcf_engine.py grows too large, split into:
src/dcf/
├── __init__.py
├── wacc.py          # WACC calculations
├── free_cash_flow.py
├── terminal_value.py
└── valuation.py     # Main DCF logic
```

## Performance & Optimization

### When to Optimize
1. **Profile first**: Never optimize without data
2. **After correctness**: Code must be correct before optimizing
3. **When it matters**: User-facing operations >1 second
4. **Benchmark**: Establish baseline before changes

### Profiling Workflow
```bash
# Profile CPU usage
python -m cProfile -o profile.prof main.py
python -m pstats profile.prof
# (pstats) sort cumulative
# (pstats) stats 20

# Profile memory
pip install memory-profiler
python -m memory_profiler main.py

# Line profiling
pip install line-profiler
kernprof -l -v main.py
```

### Optimization Techniques

**Vectorization** (Critical for NumPy/Pandas)
```python
# BAD: Python loops
results = []
for i in range(len(df)):
    result = df.iloc[i]['value'] * 1.1
    results.append(result)

# GOOD: Vectorized
results = df['value'] * 1.1

# BAD: iterrows()
for idx, row in df.iterrows():
    df.at[idx, 'result'] = row['value'] * 1.1

# GOOD: vectorized operation
df['result'] = df['value'] * 1.1
```

**Caching**
```python
from functools import lru_cache

@lru_cache(maxsize=128)
def calculate_beta(ticker: str) -> float:
    """Cache beta calculations - expensive API calls."""
    return fetch_beta_from_api(ticker)

# Clear cache when needed
calculate_beta.cache_clear()
```

**NumPy Optimization**
```python
# Use appropriate dtypes
df['price'] = df['price'].astype('float32')  # vs float64
df['ticker'] = df['ticker'].astype('category')  # for repeated strings

# Pre-allocate arrays
results = np.empty(10_000, dtype=np.float64)
for i in range(10_000):
    results[i] = calculate(i)

# vs appending (slow)
results = []
for i in range(10_000):
    results.append(calculate(i))
```

## Finance-Specific Guidelines

### DCF Calculations

**Precision for Monetary Values**
```python
from decimal import Decimal, getcontext

# Set precision for financial calculations
getcontext().prec = 10

# Use Decimal for monetary calculations
fair_value = Decimal('165.42')
shares_outstanding = Decimal('2_500_000_000')
market_cap = fair_value * shares_outstanding
```

**Validation & Edge Cases**
```python
def calculate_terminal_value(fcf: float, growth: float, wacc: float) -> float:
    """Calculate terminal value with robust validation."""
    # Validate inputs
    if growth >= wacc:
        raise ValueError(
            f"Terminal growth rate ({growth:.2%}) must be less than "
            f"WACC ({wacc:.2%}) to avoid infinite valuation"
        )
    
    if growth < 0:
        logger.warning(f"Negative growth rate ({growth:.2%}) detected, clamping to 0%")
        growth = 0.0
    
    if growth > 0.05:
        logger.warning(
            f"Terminal growth rate ({growth:.2%}) exceeds typical GDP growth, "
            f"consider capping at 5%"
        )
    
    return fcf * (1 + growth) / (wacc - growth)
```

### Data Quality & Validation

**Input Validation**
```python
from pydantic import BaseModel, Field, validator

class DCFInputs(BaseModel):
    """Validated DCF calculation inputs."""
    
    ticker: str = Field(..., min_length=1, max_length=10)
    projection_years: int = Field(..., ge=3, le=10)
    terminal_growth: float = Field(..., ge=0.0, le=0.10)
    tax_rate: float = Field(..., ge=0.0, le=0.5)
    
    @validator('terminal_growth')
    def validate_growth(cls, v):
        if v > 0.05:
            logging.warning(f"High terminal growth rate: {v:.2%}")
        return v
    
    @validator('ticker')
    def uppercase_ticker(cls, v):
        return v.upper().strip()
```

**Missing Data Handling**
```python
def handle_missing_financials(df: pd.DataFrame) -> pd.DataFrame:
    """Handle missing financial data with explicit strategy."""
    # Check for critical missing values
    critical_cols = ['revenue', 'operating_income', 'total_debt']
    missing = df[critical_cols].isna().sum()
    
    if missing.any():
        logger.error(f"Critical financial data missing: {missing[missing > 0]}")
        raise ValueError("Cannot proceed with incomplete financial data")
    
    # Forward fill non-critical columns
    df['capex'] = df['capex'].ffill()
    
    # Document imputation
    logger.info("Applied forward-fill to CapEx data for missing quarters")
    
    return df
```

### Security

**Environment Variables**
```python
import os
from dotenv import load_dotenv

load_dotenv('config/secrets.env')

# NEVER do this
API_KEY = "sk-1234567890abcdef"  # WRONG!

# ALWAYS use environment variables
API_KEY = os.getenv('FRED_API_KEY')
if not API_KEY:
    raise ValueError("FRED_API_KEY environment variable not set")
```

**Input Sanitization**
```python
def sanitize_ticker(ticker: str) -> str:
    """Sanitize user-provided ticker symbols."""
    # Remove special characters, prevent injection
    ticker = ticker.upper().strip()
    if not ticker.isalnum():
        raise ValueError(f"Invalid ticker format: {ticker}")
    if len(ticker) > 10:
        raise ValueError(f"Ticker too long: {ticker}")
    return ticker
```

## Error Handling

### Exception Hierarchy
```python
# src/exceptions.py
class DCFError(Exception):
    """Base exception for DCF calculations."""
    pass

class ValidationError(DCFError):
    """Invalid input data."""
    pass

class CalculationError(DCFError):
    """Error during calculation."""
    pass

class DataFetchError(DCFError):
    """Failed to retrieve external data."""
    pass
```

### Error Handling Patterns
```python
def calculate_dcf(ticker: str) -> float:
    """Calculate DCF with comprehensive error handling."""
    try:
        # Validate inputs
        ticker = sanitize_ticker(ticker)
        
        # Fetch data
        financials = fetch_financials(ticker)
        
    except requests.Timeout:
        logger.error(f"Timeout fetching data for {ticker}")
        raise DataFetchError(f"API timeout for {ticker}") from None
        
    except ValueError as e:
        logger.error(f"Invalid input: {e}")
        raise ValidationError(str(e)) from e
        
    except Exception as e:
        logger.critical(f"Unexpected error calculating DCF: {e}", exc_info=True)
        raise CalculationError(f"DCF calculation failed for {ticker}") from e
```

## Continuous Integration

### Pre-commit Hooks (Required)
All developers must install pre-commit hooks:
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

### GitHub Actions / CI Pipeline
```yaml
# Minimum CI checks (if implemented)
- Ruff linting must pass
- Mypy type checking must pass
- All tests must pass (pytest)
- Coverage must be >85%
- No security vulnerabilities (pip-audit)
```

## Version Control Workflow

### Pull Request Requirements
- Descriptive title using conventional commit format
- Link to related issue: `Closes #123`, `Fixes #456`
- Description of changes (what and why)
- All CI checks passing
- At least one approval from code owner
- Test coverage maintained or improved

### Code Review Checklist
- [ ] Tests cover new functionality
- [ ] Docstrings present and accurate
- [ ] No hardcoded credentials or API keys
- [ ] Type hints on all function signatures
- [ ] Commit messages follow conventional commits
- [ ] No breaking changes without `BREAKING CHANGE:` footer
- [ ] Performance implications considered for large datasets
