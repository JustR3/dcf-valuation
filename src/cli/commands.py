"""CLI command handlers for DCF toolkit.

Each function handles a specific CLI subcommand, processing args and orchestrating
the appropriate engine calls and display output.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from src.cli.display import (
    print_header,
    print_msg,
    display_valuation,
    display_scenarios,
    display_sensitivity,
    display_stress_test,
    display_comparison,
    display_portfolio,
    export_csv,
    enrich_dcf_with_monte_carlo,
)
from src.cli.interactive import run_valuation_interactive, run_portfolio_interactive
from src.dcf_engine import DCFEngine
from src.optimizer import OptimizationMethod
from src.portfolio import optimize_portfolio_with_dcf
from src.regime import RegimeDetector


# =============================================================================
# Valuation Command Handler
# =============================================================================

def handle_valuation_command(args: Namespace) -> None:
    """Handle valuation/dcf/val command.
    
    Supports:
    - Single ticker DCF valuation
    - Multi-ticker comparison (--compare flag or compare command)
    - Scenario analysis (--scenarios)
    - Sensitivity analysis (--sensitivity)
    - Stress test (--stress)
    """
    print_header("DCF Valuation Engine")

    if not args.tickers:
        run_valuation_interactive()
        return

    tickers = [t.upper().strip() for t in args.tickers]

    # Multi-stock comparison
    if args.compare and len(tickers) > 1:
        print_msg(f"Comparing {len(tickers)} stocks...")
        comparison = DCFEngine.compare_stocks(
            tickers,
            growth=args.growth / 100 if args.growth else None,
            term_growth=args.terminal_growth / 100,
            wacc=args.wacc / 100 if args.wacc else None,
            years=args.years,
        )
        display_comparison(comparison)
        if args.export:
            export_csv(comparison, args.export)
        return

    # Single ticker analysis
    ticker = tickers[0]
    print_msg(f"Analyzing {ticker}...")

    engine = DCFEngine(ticker, auto_fetch=True)
    if not engine.is_ready:
        print_msg(f"Error: {engine.last_error}", "error")
        sys.exit(1)

    print_msg("Data loaded!", "success")

    # Parse parameters
    growth = args.growth / 100 if args.growth else None
    term = args.terminal_growth / 100
    wacc = args.wacc / 100 if args.wacc else None

    try:
        if args.scenarios:
            display_scenarios(
                engine.run_scenario_analysis(
                    base_growth=growth,
                    base_term_growth=term,
                    base_wacc=wacc,
                    years=args.years
                ),
                ticker
            )
        elif args.sensitivity:
            display_sensitivity(
                engine.run_sensitivity_analysis(
                    base_growth=growth,
                    base_term_growth=term,
                    base_wacc=wacc,
                    years=args.years
                ),
                ticker
            )
        elif args.stress:
            display_stress_test(engine.run_stress_test(years=args.years))
        else:
            display_valuation(
                engine.get_intrinsic_value(
                    growth=growth,
                    term_growth=term,
                    wacc=wacc,
                    years=args.years
                ),
                engine,
                detailed=args.detailed
            )
    except Exception as e:
        print_msg(f"Error: {e}", "error")
        sys.exit(1)


# =============================================================================
# Compare Command Handler
# =============================================================================

def handle_compare_command(args: Namespace) -> None:
    """Handle compare command (alias for valuation --compare).
    
    Requires at least 2 tickers.
    """
    if not args.tickers or len(args.tickers) < 2:
        print_msg("Compare command requires at least 2 tickers", "error")
        sys.exit(1)
    
    # Set compare flag and route to valuation handler
    args.compare = True
    handle_valuation_command(args)


# =============================================================================
# Portfolio Command Handler
# =============================================================================

def handle_portfolio_command(args: Namespace) -> None:
    """Handle portfolio/port command.
    
    Runs DCF-based portfolio optimization with:
    - Black-Litterman views from DCF valuations
    - Monte Carlo enrichment for conviction ratings
    - Market regime detection for risk adjustment
    """
    if not args.tickers:
        run_portfolio_interactive()
        return
    
    print_header("DCF-Based Portfolio Optimization")
    tickers = [t.upper().strip() for t in args.tickers]
    print_msg(f"Analyzing {len(tickers)} stocks...")

    # DCF analysis with full enrichment
    dcf_results = {}
    for ticker in tickers:
        try:
            engine = DCFEngine(ticker, auto_fetch=True)
            if engine.is_ready:
                result = engine.get_intrinsic_value(
                    growth=args.growth / 100 if args.growth else None,
                    term_growth=args.terminal_growth / 100,
                    wacc=args.wacc / 100 if args.wacc else None,
                    years=args.years
                )
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
        sys.exit(1)

    # Regime detection
    print_msg("Detecting market regime...")
    regime = RegimeDetector().get_current_regime()
    print_msg(f"Regime: {regime}", "success")

    # Map method string to enum
    method_map = {
        "max_sharpe": OptimizationMethod.MAX_SHARPE,
        "min_volatility": OptimizationMethod.MIN_VOLATILITY,
        "equal_weight": OptimizationMethod.EQUAL_WEIGHT
    }
    method = method_map.get(args.method, OptimizationMethod.MAX_SHARPE)

    print_msg(f"Optimizing with {method.value}...")
    result = optimize_portfolio_with_dcf(dcf_results, method=method)

    if result:
        result_dict = result.to_dict()
        result_dict['dcf_results'] = dcf_results
        display_portfolio(result_dict, regime=regime.value)
    else:
        # Try to get more specific error
        from src.portfolio import DCFPortfolioOptimizer
        test_engine = DCFPortfolioOptimizer(list(dcf_results.keys()))
        test_engine.fetch_data()
        test_engine.optimize_with_dcf_views(dcf_results, method=method)
        error_msg = (
            test_engine._last_error 
            if hasattr(test_engine, '_last_error') and test_engine._last_error 
            else "Unknown error"
        )
        print_msg(f"Optimization failed: {error_msg}", "error")
        sys.exit(1)
