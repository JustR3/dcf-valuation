"""CLI module for DCF Valuation Toolkit.

Provides display formatting, interactive prompts, and command handlers.
"""

from src.cli.display import (
    print_header,
    print_msg,
    display_valuation,
    display_scenarios,
    display_comparison,
    display_sensitivity,
    display_stress_test,
    display_portfolio,
    export_csv,
)
from src.cli.interactive import (
    get_params_interactive,
    run_valuation_interactive,
    run_portfolio_interactive,
)
from src.cli.commands import (
    handle_valuation_command,
    handle_portfolio_command,
    handle_compare_command,
)

__all__ = [
    # Display
    "print_header",
    "print_msg",
    "display_valuation",
    "display_scenarios",
    "display_comparison",
    "display_sensitivity",
    "display_stress_test",
    "display_portfolio",
    "export_csv",
    # Interactive
    "get_params_interactive",
    "run_valuation_interactive",
    "run_portfolio_interactive",
    # Commands
    "handle_valuation_command",
    "handle_portfolio_command",
    "handle_compare_command",
]
