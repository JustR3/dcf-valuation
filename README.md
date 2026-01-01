# DCF Valuation Toolkit

A comprehensive Discounted Cash Flow (DCF) valuation tool for fundamental stock analysis and portfolio optimization.

## 🎯 Overview

This toolkit implements sophisticated DCF valuation with Monte Carlo simulation, market regime detection, and Black-Litterman portfolio optimization. Built for fundamental analysts and value investors who need rigorous cash flow analysis combined with quantitative portfolio construction.

## ✨ Key Features

### 📊 DCF Valuation Engine
- **Free Cash Flow Projection**: 5-year forecasts with analyst estimates
- **WACC Calculation**: CAPM-based with sector-specific betas
- **Terminal Value Methods**: Perpetuity growth & exit multiples
- **Monte Carlo Simulation**: 3,000-5,000 iterations for probabilistic valuation
- **Reverse DCF**: Calculate implied growth rates from current price
- **Sensitivity Analysis**: Stress testing across growth/WACC scenarios
- **EV/Sales Fallback**: Relative valuation for negative FCF companies

### 💼 Portfolio Optimization
- **Black-Litterman Framework**: Bayesian optimization with DCF-derived views
- **Market Regime Detection**: Bull/Bear/Transition classification
- **Multiple Objectives**: Max Sharpe, Min Volatility, Max Quadratic Utility
- **Position Sizing**: Optimal weights with conviction-based allocation

### 🎨 Interactive CLI
- **Rich Terminal UI**: Beautiful tables and formatted output
- **Command Mode**: Script-friendly for automation
- **Multi-Stock Comparison**: Side-by-side valuation analysis
- **CSV Export**: Results export for further analysis

## 🚀 Quick Start

### Installation

This project uses [UV](https://docs.astral.sh/uv/) for fast, reliable Python package management.

```bash
# Clone the repository
git clone https://github.com/JustR3/dcf-valuation.git
cd dcf-valuation

# Install UV if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies (creates .venv automatically)
uv sync
```

### Usage

**Single Stock Valuation:**
```bash
uv run python dcf.py valuation AAPL
```

**Multi-Stock Comparison:**
```bash
uv run python dcf.py compare AAPL MSFT GOOGL AMZN
```

**Portfolio Optimization:**
```bash
uv run python dcf.py portfolio AAPL MSFT GOOGL --method max_sharpe
```

### Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest tests/ -v

# Run linter
uv run ruff check src/

# Format code
uv run ruff format src/
```

## 📦 Project Structure

```
dcf-valuation/
├── dcf.py                 # Main CLI entry point
├── src/
│   ├── dcf_engine.py      # Core DCF valuation engine
│   ├── portfolio.py       # DCF-aware portfolio optimizer
│   ├── optimizer.py       # Black-Litterman implementation
│   ├── regime.py          # Market regime detection
│   ├── utils.py           # Caching & rate limiting
│   └── config.py          # Configuration constants
├── data/
│   └── cache/             # Cached financial data
├── tests/                 # Unit tests
├── README.md
├── LICENSE
└── pyproject.toml
```

## 🔬 Methodology

### DCF Calculation

1. **Free Cash Flow (FCF)**: Extracted from company financials (TTM)
2. **Growth Rates**: Analyst estimates + Bayesian prior cleaning
3. **WACC**: Risk-free rate + Beta × Market risk premium
4. **PV of FCF**: Discount projected cash flows
5. **Terminal Value**: Perpetuity growth method
6. **Fair Value**: Sum of PV(FCF) + PV(Terminal Value) / Shares Outstanding

### Monte Carlo Simulation

Simulates 3,000+ scenarios varying:
- Growth rates (±20% volatility)
- WACC (±10% volatility)
- Terminal growth (±5% volatility)

Provides probabilistic range: 10th/90th percentiles, mean, median, std dev.

### Portfolio Optimization

1. **Historical Returns**: Fetch price data (1-year lookback)
2. **DCF Views**: Convert upside % to expected return views
3. **Market Regime**: Adjust confidence based on bull/bear state
4. **Black-Litterman**: Combine market equilibrium + DCF views
5. **Optimize**: Max Sharpe ratio with constraints (max 30% per position)

## 🧪 Testing

```bash
pytest tests/
```

## 📊 Example Output

```
╭────────────────────────────────────────╮
│ DCF Valuation: AAPL                    │
├─────────────────────┬──────────────────┤
│ Metric              │            Value │
├─────────────────────┼──────────────────┤
│ Current Price       │          $175.50 │
│ Fair Value (DCF)    │          $198.32 │
│ Upside              │          +13.01% │
│ WACC                │            8.50% │
│                     │                  │
│ Monte Carlo (3,000) │                  │
│   Mean              │          $195.78 │
│   Median            │          $197.12 │
│   10th Percentile   │          $165.44 │
│   90th Percentile   │          $225.91 │
╰─────────────────────┴──────────────────╯

Conviction: Buy
```

## ⚙️ Configuration

Edit [src/config.py](src/config.py) to customize:

- Monte Carlo iterations (default: 3,000)
- Growth rate bounds (-50% to +100%)
- WACC parameters (risk-free rate, market premium)
- Terminal growth rate (default: 2.5%)
- Sector-specific exit multiples
- Portfolio constraints (max 30% per position)

## 📚 Data Sources

- **yfinance**: Company financials, prices, analyst estimates
- **Consolidated Cache**: Single Parquet file per ticker (24h expiry)
- **Rate Limiting**: 60 calls/minute to respect API limits

## 🔧 Advanced Features

### Reverse DCF
Calculate implied growth rate from current market price:
```python
from src.dcf_engine import DCFEngine
engine = DCFEngine("AAPL")
implied_growth = engine.reverse_dcf(target_price=175.50)
```

### Scenario Analysis
Test Bull/Base/Bear cases:
```python
scenarios = engine.scenario_analysis()
# Returns: {bull: {...}, base: {...}, bear: {...}}
```

### Sensitivity Heatmap
Stress test across growth/WACC ranges:
```python
sensitivity = engine.sensitivity_analysis()
# 2D grid of fair values
```

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- **Damodaran**: Sector priors and valuation methodologies
- **PyPortfolioOpt**: Portfolio optimization framework
- **yfinance**: Yahoo Finance API wrapper

## 📧 Contact

For questions or feedback, open an issue on GitHub.

---

**Disclaimer:** This tool is for educational and research purposes. Not financial advice. Always conduct your own due diligence before making investment decisions.
