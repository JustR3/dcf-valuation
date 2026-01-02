#!/usr/bin/env python3
"""DCF Valuation Toolkit - Thin CLI Entry Point.

This module provides the command-line interface for the DCF valuation toolkit.
All heavy lifting is delegated to modular components in src/.

Usage Examples:
    # Interactive mode
    uv run dcf.py
    
    # Single stock valuation
    uv run dcf.py valuation AAPL
    uv run dcf.py dcf AAPL --detailed
    uv run dcf.py val AAPL --scenarios
    uv run dcf.py val AAPL --stress
    
    # Multi-stock comparison
    uv run dcf.py compare AAPL MSFT GOOGL
    uv run dcf.py val AAPL MSFT GOOGL --compare
    
    # Portfolio optimization
    uv run dcf.py portfolio AAPL MSFT GOOGL NVDA
    uv run dcf.py port AAPL MSFT --method min_volatility
"""

from __future__ import annotations

import argparse
import sys

# Check for Rich/Questionary availability
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

# Import CLI components
from src.cli.commands import (
    handle_valuation_command,
    handle_portfolio_command,
    handle_compare_command,
)
from src.cli.interactive import (
    run_valuation_interactive,
    run_portfolio_interactive,
)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="DCF Valuation Toolkit - Fundamental Analysis",
        epilog="For full documentation: https://github.com/your-repo/dcf-valuation"
    )

    parser.add_argument(
        "command",
        nargs='?',
        choices=["valuation", "val", "dcf", "portfolio", "port", "compare"],
        help="Command to run (omit for interactive mode)"
    )
    parser.add_argument("tickers", nargs="*", help="Stock ticker(s)")

    # DCF parameters
    parser.add_argument("-g", "--growth", type=float,
                       help="Annual growth rate (percent)")
    parser.add_argument("-t", "--terminal-growth", type=float, default=2.5,
                       help="Terminal growth rate (percent, default: 2.5)")
    parser.add_argument("-w", "--wacc", type=float,
                       help="WACC (percent)")
    parser.add_argument("-y", "--years", type=int, default=5,
                       help="Forecast years")

    # Analysis modes
    parser.add_argument("--scenarios", action="store_true",
                       help="Run scenario analysis")
    parser.add_argument("--sensitivity", action="store_true",
                       help="Run sensitivity analysis")
    parser.add_argument("--stress", action="store_true",
                       help="Run stress test")
    parser.add_argument("--compare", "-c", action="store_true",
                       help="Compare multiple stocks")
    parser.add_argument("--detailed", action="store_true",
                       help="Show detailed technical breakdown")

    # Portfolio options
    parser.add_argument("--method", type=str,
                       choices=["max_sharpe", "min_volatility", "equal_weight"],
                       default="max_sharpe",
                       help="Portfolio optimization method")

    # Output options
    parser.add_argument("--export", type=str,
                       help="Export results to CSV")

    return parser


def run_interactive_menu() -> None:
    """Run interactive main menu."""
    if HAS_QUESTIONARY and questionary:
        choice = questionary.select(
            "What would you like to do?",
            choices=["Stock Valuation", "Portfolio Optimization", "Exit"],
            style=custom_style
        ).ask()

        if choice == "Stock Valuation":
            run_valuation_interactive()
        elif choice == "Portfolio Optimization":
            run_portfolio_interactive()
    else:
        print("\nDCF Valuation Toolkit")
        print("1. Stock Valuation")
        print("2. Portfolio Optimization")
        choice = input("\nChoice (1-2): ").strip()

        if choice == "1":
            run_valuation_interactive()
        elif choice == "2":
            run_portfolio_interactive()


def main() -> None:
    """DCF CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Interactive mode (no command specified)
    if not args.command:
        run_interactive_menu()
        return

    # Route to appropriate command handler
    if args.command in ("portfolio", "port"):
        handle_portfolio_command(args)
        
    elif args.command == "compare":
        handle_compare_command(args)
        
    elif args.command in ("valuation", "val", "dcf"):
        handle_valuation_command(args)


if __name__ == "__main__":
    main()
