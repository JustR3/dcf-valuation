"""Interactive CLI prompts for DCF toolkit.

Handles user input collection via Questionary (if available) or fallback input().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.dcf_engine import DCFEngine

try:
    import questionary
    from questionary import Style
    HAS_QUESTIONARY = True
    custom_style = Style([
        ("qmark", "fg:cyan bold"),
        ("question", "bold"),
        ("answer", "fg:cyan bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:cyan"),
    ])
except ImportError:
    HAS_QUESTIONARY = False
    questionary = None
    custom_style = None

from src.cli.display import (
    print_header,
    print_msg,
    display_valuation,
    display_scenarios,
    display_sensitivity,
    display_portfolio,
    enrich_dcf_with_monte_carlo,
)
from src.dcf_engine import DCFEngine
from src.optimizer import OptimizationMethod
from src.portfolio import optimize_portfolio_with_dcf
from src.regime import RegimeDetector


# =============================================================================
# Parameter Collection
# =============================================================================

def get_params_interactive(data: dict) -> dict:
    """Get DCF parameters interactively.
    
    Args:
        data: Company data dict with current_price, beta, analyst_growth etc.
        
    Returns:
        Dict with growth, term_growth, wacc, years parameters.
    """
    print_msg(f"Loaded {data['ticker']} | Price: ${data['current_price']:.2f} | Beta: {data['beta']:.2f}")

    analyst = data.get("analyst_growth")
    default_growth = (analyst * 100) if analyst else 5.0
    default_wacc = 4.5 + (data.get("beta", 1.0) * 7.0)

    if HAS_QUESTIONARY and questionary:
        growth = float(questionary.text(
            f"Growth % [{default_growth:.1f}]:",
            default=str(default_growth),
            style=custom_style
        ).ask() or default_growth) / 100
        
        term = float(questionary.text(
            "Terminal % [2.5]:",
            default="2.5",
            style=custom_style
        ).ask() or 2.5) / 100
        
        wacc = float(questionary.text(
            f"WACC % [{default_wacc:.1f}]:",
            default=str(round(default_wacc, 1)),
            style=custom_style
        ).ask() or default_wacc) / 100
        
        years = int(questionary.text(
            "Years [5]:",
            default="5",
            style=custom_style
        ).ask() or 5)
    else:
        growth = float(input(f"Growth % [{default_growth:.1f}]: ").strip() or default_growth) / 100
        term = float(input("Terminal % [2.5]: ").strip() or 2.5) / 100
        wacc = float(input(f"WACC % [{default_wacc:.1f}]: ").strip() or default_wacc) / 100
        years = int(input("Years [5]: ").strip() or 5)

    return {"growth": growth, "term_growth": term, "wacc": wacc, "years": years}


# =============================================================================
# Interactive Valuation Flow
# =============================================================================

def run_valuation_interactive() -> None:
    """Run interactive stock valuation flow."""
    if HAS_QUESTIONARY and questionary:
        ticker = questionary.text("Ticker:", style=custom_style).ask()
    else:
        ticker = input("Ticker: ").strip()
        
    if not ticker:
        print_msg("Invalid ticker", "error")
        return

    ticker = ticker.upper().strip()
    print_msg(f"Fetching {ticker}...")

    engine = DCFEngine(ticker, auto_fetch=True)
    if not engine.is_ready:
        print_msg(f"Error: {engine.last_error}", "error")
        return

    print_msg("Data loaded!", "success")

    # Analysis type selection
    choices = ["1. Standard DCF", "2. Scenario Analysis", "3. Sensitivity Analysis"]
    
    if HAS_QUESTIONARY and questionary:
        choice = questionary.select(
            "Analysis type:",
            choices=choices,
            style=custom_style
        ).ask()
    else:
        print("\n".join(f"  {c}" for c in choices))
        choice = input("Choice (1-3): ").strip()

    params = get_params_interactive(engine.company_data.to_dict())

    try:
        if "1" in choice or "Standard" in choice:
            display_valuation(engine.get_intrinsic_value(**params), engine)
            
        elif "2" in choice or "Scenario" in choice:
            # Remap params for scenario analysis
            scenario_params = {
                'base_growth': params['growth'],
                'base_term_growth': params['term_growth'],
                'base_wacc': params['wacc'],
                'years': params['years']
            }
            display_scenarios(engine.run_scenario_analysis(**scenario_params), ticker)
            
        elif "3" in choice or "Sensitivity" in choice:
            # Remap params for sensitivity analysis
            sensitivity_params = {
                'base_growth': params['growth'],
                'base_term_growth': params['term_growth'],
                'base_wacc': params['wacc'],
                'years': params['years']
            }
            display_sensitivity(engine.run_sensitivity_analysis(**sensitivity_params), ticker)
            
    except Exception as e:
        print_msg(f"Error: {e}", "error")


# =============================================================================
# Interactive Portfolio Flow
# =============================================================================

def run_portfolio_interactive() -> None:
    """Run interactive portfolio optimization flow."""
    print_header("DCF-Based Portfolio Optimization")

    default = "AAPL,MSFT,GOOGL,NVDA"
    
    if HAS_QUESTIONARY and questionary:
        tickers_input = questionary.text(
            f"Tickers (comma-separated) [{default}]:",
            default=default,
            style=custom_style
        ).ask()
    else:
        tickers_input = input(f"Tickers [{default}]: ").strip() or default

    tickers = [t.strip().upper() for t in tickers_input.split(",")]
    print_msg(f"Analyzing {len(tickers)} stocks...")

    # DCF analysis with full enrichment
    dcf_results = {}
    for ticker in tickers:
        try:
            engine = DCFEngine(ticker, auto_fetch=True)
            if engine.is_ready:
                result = engine.get_intrinsic_value()
                enriched_result = enrich_dcf_with_monte_carlo(engine, result)
                dcf_results[ticker] = enriched_result

                upside = enriched_result['upside_downside']
                conviction = enriched_result.get('conviction', {})
                conv_emoji = conviction.get('emoji', '⚪')
                conv_label = conviction.get('label', 'N/A')

                status = "🟢" if upside > 20 else "🔴" if upside < -20 else "🟡"
                print_msg(
                    f"{ticker}: ${enriched_result['value_per_share']:.2f} ({upside:+.1f}%) "
                    f"{status} {conv_emoji} {conv_label}",
                    "success"
                )
            else:
                print_msg(f"{ticker}: {engine.last_error}", "error")
        except Exception as e:
            print_msg(f"{ticker}: {e}", "error")

    if not dcf_results:
        print_msg("No valid DCF results", "error")
        return

    # Regime detection
    print_msg("Detecting market regime...")
    regime = RegimeDetector().get_current_regime()
    print_msg(f"Regime: {regime}", "success")

    # Optimization method selection
    method_choices = [
        "1. Max Sharpe (Best risk-adjusted returns)",
        "2. Min Volatility (Lowest risk)",
        "3. Equal Weight (Diversified)"
    ]

    if HAS_QUESTIONARY and questionary:
        method_choice = questionary.select(
            "Optimization objective:",
            choices=method_choices,
            style=custom_style
        ).ask()
    else:
        print("\nOptimization Objectives:")
        print("\n".join(f"  {c}" for c in method_choices))
        method_choice = input("Choice (1-3) [1]: ").strip() or "1"

    method_map = {
        "1": OptimizationMethod.MAX_SHARPE,
        "2": OptimizationMethod.MIN_VOLATILITY,
        "3": OptimizationMethod.EQUAL_WEIGHT
    }

    # Find matching method
    method = OptimizationMethod.MAX_SHARPE  # default
    for key, value in method_map.items():
        if key in method_choice:
            method = value
            break

    print_msg(f"Optimizing with {method.value}...")
    result = optimize_portfolio_with_dcf(dcf_results, method=method)

    if result:
        result_dict = result.to_dict()
        result_dict['dcf_results'] = dcf_results
        display_portfolio(result_dict, regime=regime.value)
    else:
        print_msg("Optimization failed", "error")
