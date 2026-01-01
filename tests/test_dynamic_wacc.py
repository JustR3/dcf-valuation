"""Test script for dynamic WACC calculation with Treasury yield and CAPE adjustments."""

from src.dcf_engine import DCFEngine
from src.regime import (
    get_10year_treasury_yield,
    get_current_cape,
    get_dynamic_risk_free_rate,
    calculate_cape_wacc_adjustment
)
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def display_wacc_breakdown(ticker: str):
    """Display detailed WACC breakdown with dynamic components."""
    console.print(f"\n[bold cyan]═══ WACC Analysis: {ticker} ═══[/bold cyan]\n")
    
    # Create DCF engine
    engine = DCFEngine(ticker)
    if not engine.is_ready:
        console.print(f"[red]Failed to fetch data for {ticker}[/red]")
        return
    
    # Get WACC breakdown
    breakdown = engine.get_wacc_breakdown(
        use_dynamic_rf=True,
        use_cape_adjustment=True
    )
    
    # Display risk-free rate section
    console.print(Panel(
        f"[bold]Source:[/bold] {breakdown['rf_source']}\n"
        f"[bold]Rate:[/bold] {breakdown['risk_free_rate']*100:.2f}%",
        title="📊 Risk-Free Rate (10Y Treasury)",
        border_style="cyan"
    ))
    
    # Display CAPE section
    if breakdown.get('cape_info'):
        cape = breakdown['cape_info']
        color = "green" if cape['market_state'] == "CHEAP" else "red" if cape['market_state'] == "EXPENSIVE" else "yellow"
        console.print(Panel(
            f"[bold]CAPE Ratio:[/bold] {cape['cape_ratio']:.1f}\n"
            f"[bold]Market State:[/bold] [{color}]{cape['market_state']}[/{color}]\n"
            f"[bold]WACC Adjustment:[/bold] {cape['adjustment_bps']:+.0f} bps",
            title="🌍 Shiller CAPE Macro Adjustment",
            border_style=color
        ))
    
    # Create WACC components table
    table = Table(title="WACC Components Breakdown", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Value", justify="right", style="bold")
    table.add_column("Contribution", justify="right")
    
    table.add_row(
        "Risk-Free Rate",
        f"{breakdown['risk_free_rate']*100:.2f}%",
        f"{breakdown['components']['rf_contribution']*100:.2f}%"
    )
    table.add_row(
        f"Beta × Market Risk Premium",
        f"{breakdown['beta']:.2f} × {breakdown['market_risk_premium']*100:.1f}%",
        f"{breakdown['components']['beta_contribution']*100:.2f}%"
    )
    table.add_row(
        "CAPE Adjustment",
        f"{breakdown['cape_adjustment']*10000:+.0f} bps",
        f"{breakdown['components']['cape_contribution']*100:+.2f}%",
        style="dim"
    )
    table.add_row(
        "───────────────",
        "───────────",
        "───────────",
        style="dim"
    )
    table.add_row(
        "[bold]Base WACC[/bold]",
        f"[bold]{breakdown['base_wacc']*100:.2f}%[/bold]",
        "",
        style="yellow"
    )
    table.add_row(
        "[bold]Final WACC[/bold]",
        f"[bold]{breakdown['final_wacc']*100:.2f}%[/bold]",
        "",
        style="green bold"
    )
    
    console.print(table)
    
    # Compare with static WACC
    static_wacc = engine.calculate_wacc(use_dynamic_rf=False, use_cape_adjustment=False)
    delta = (breakdown['final_wacc'] - static_wacc) * 10000
    
    console.print(f"\n[dim]Static WACC (config): {static_wacc*100:.2f}%[/dim]")
    console.print(f"[dim]Difference: {delta:+.0f} bps[/dim]\n")


def display_macro_summary():
    """Display current macro environment summary."""
    console.print("\n[bold magenta]═══ Current Macro Environment ═══[/bold magenta]\n")
    
    # Treasury yield
    treasury_yield = get_10year_treasury_yield()
    if treasury_yield:
        console.print(f"[cyan]📈 10-Year Treasury Yield:[/cyan] {treasury_yield*100:.2f}%")
    else:
        console.print("[yellow]⚠️  Could not fetch Treasury yield[/yellow]")
    
    # CAPE ratio
    cape_data = get_current_cape()
    if cape_data:
        color = "green" if cape_data.market_state == "CHEAP" else "red" if cape_data.market_state == "EXPENSIVE" else "yellow"
        console.print(f"[cyan]🌍 Shiller CAPE Ratio:[/cyan] [{color}]{cape_data.cape_ratio:.1f} ({cape_data.market_state})[/{color}]")
        
        # Historical context
        if cape_data.cape_ratio < 15:
            context = "Market is [green]undervalued[/green] vs historical average (~16-17)"
        elif cape_data.cape_ratio > 30:
            context = "Market is [red]overvalued[/red] vs historical average (~16-17)"
        else:
            context = "Market is [yellow]fairly valued[/yellow] vs historical average (~16-17)"
        console.print(f"   {context}")
    else:
        console.print("[yellow]⚠️  Could not fetch CAPE data[/yellow]")
    
    # CAPE adjustment
    cape_adj = calculate_cape_wacc_adjustment()
    if cape_adj != 0:
        direction = "increasing" if cape_adj > 0 else "decreasing"
        console.print(f"[cyan]⚙️  WACC Adjustment:[/cyan] {cape_adj*10000:+.0f} bps ({direction} discount rate)")
    else:
        console.print("[cyan]⚙️  WACC Adjustment:[/cyan] No adjustment (fair market)")
    
    console.print()


if __name__ == "__main__":
    # Display macro environment first
    display_macro_summary()
    
    # Test with different stocks
    test_tickers = ["AAPL", "NVDA", "MSFT"]
    
    for ticker in test_tickers:
        try:
            display_wacc_breakdown(ticker)
        except Exception as e:
            console.print(f"[red]Error analyzing {ticker}: {e}[/red]\n")
    
    console.print("[green]✓ Dynamic WACC analysis complete![/green]\n")
