"""
Deep analysis of Monte Carlo simulation assumptions for Johnson & Johnson (JNJ).

This script dissects the Monte Carlo simulation to understand:
1. What assumptions are being made
2. How scenarios are distributed (Bear/Base/Bull)
3. What the input parameters are for each simulation
4. Whether "garbage in, garbage out" is happening
"""

import numpy as np
import pandas as pd
from src.dcf_engine import DCFEngine
from src.logging_config import get_logger

logger = get_logger(__name__)


def analyze_monte_carlo_inputs(ticker: str = "JNJ", iterations: int = 1000):
    """
    Analyze what goes INTO the Monte Carlo simulation for a given stock.
    
    This is critical for understanding GIGO (garbage in, garbage out).
    """
    print("=" * 100)
    print(f"MONTE CARLO SIMULATION DEEP DIVE: {ticker}")
    print("=" * 100)
    
    # Initialize DCF engine
    engine = DCFEngine(ticker, auto_fetch=True)
    
    if not engine.is_ready:
        print(f"❌ Failed to load data for {ticker}: {engine._last_error}")
        return
    
    data = engine._company_data
    
    print("\n" + "=" * 100)
    print("SECTION 1: BASE CASE ASSUMPTIONS (What the model STARTS with)")
    print("=" * 100)
    
    # Get base parameters that Monte Carlo will vary
    analyst_growth = data.analyst_growth or 0.05
    sector = data.sector
    
    # Apply sector constraints (this is what the model actually uses)
    constrained_growth, warnings = engine.apply_sector_constraints(analyst_growth, sector)
    terminal_growth = engine.get_sector_terminal_growth(sector)
    wacc = engine.calculate_wacc(data.beta)
    
    # Get sector max for display
    sector_max_growth = engine.SECTOR_MAX_GROWTH.get(sector, 0.30)
    
    print(f"\n📊 Company Fundamentals:")
    print(f"   Ticker:             {ticker}")
    print(f"   Sector:             {sector}")
    print(f"   Current Price:      ${data.current_price:.2f}")
    print(f"   Market Cap:         ${data.market_cap:.2f}B")
    print(f"   Free Cash Flow:     ${data.fcf:,.0f}M")
    print(f"   Shares Outstanding: {data.shares:,.0f}M")
    
    print(f"\n📈 Growth Assumptions:")
    print(f"   Raw Analyst Growth:        {analyst_growth*100:.1f}%")
    print(f"   Sector Max Growth:         {sector_max_growth*100:.1f}% ({sector})")
    print(f"   Constrained Growth Used:   {constrained_growth*100:.1f}% ← THIS IS WHAT MONTE CARLO USES")
    if warnings:
        for warning in warnings:
            print(f"   ⚠️  {warning}")
    print(f"   Terminal Growth Rate:      {terminal_growth*100:.1f}%")
    
    print(f"\n💰 Discount Rate (WACC):")
    wacc_breakdown = engine.get_wacc_breakdown(data.beta)
    print(f"   WACC: {wacc*100:.2f}%")
    print(f"   └─ Risk-Free Rate: {wacc_breakdown['risk_free_rate']*100:.2f}% ({wacc_breakdown['rf_source']})")
    print(f"   └─ Beta: {data.beta:.2f}")
    print(f"   └─ Equity Risk Premium: {wacc_breakdown['market_risk_premium']*100:.1f}%")
    print(f"   └─ Beta × ERP: {(data.beta * wacc_breakdown['market_risk_premium'])*100:.2f}%")
    if wacc_breakdown['cape_adjustment'] != 0:
        print(f"   └─ CAPE Adjustment: {wacc_breakdown['cape_adjustment']*100:.2f}bps")
    
    print(f"\n🎯 Terminal Value Method:")
    high_growth_sectors = {"Technology", "Communication Services", "Healthcare"}
    terminal_method = "exit_multiple" if sector in high_growth_sectors else "gordon_growth"
    print(f"   Method: {terminal_method}")
    if terminal_method == "exit_multiple":
        exit_mult = engine.get_sector_exit_multiple(sector)
        print(f"   Exit Multiple: {exit_mult:.1f}x")
    
    print("\n" + "=" * 100)
    print("SECTION 2: SCENARIO DEFINITIONS (How Monte Carlo creates distributions)")
    print("=" * 100)
    
    # These are the scenarios defined in simulate_value()
    scenarios = {
        'bear': {
            'probability': 0.20,
            'growth_multiplier': 0.50,
            'terminal_multiplier': 0.6,
        },
        'base': {
            'probability': 0.60,
            'growth_multiplier': 0.80,
            'terminal_multiplier': 1.0,
        },
        'bull': {
            'probability': 0.20,
            'growth_multiplier': 1.20,
            'terminal_multiplier': 1.2,
        }
    }
    
    print("\n📊 Monte Carlo Scenario Framework:")
    print("\n   The simulation samples from 3 scenarios with different probabilities:\n")
    
    for scenario_name, scenario in scenarios.items():
        scenario_growth = constrained_growth * scenario['growth_multiplier']
        scenario_terminal = terminal_growth * scenario['terminal_multiplier']
        
        print(f"   {scenario_name.upper()} Scenario ({scenario['probability']*100:.0f}% probability):")
        print(f"      Growth Rate:    {scenario_growth*100:.1f}% (base {constrained_growth*100:.1f}% × {scenario['growth_multiplier']:.1f})")
        print(f"      Terminal Rate:  {scenario_terminal*100:.2f}% (base {terminal_growth*100:.1f}% × {scenario['terminal_multiplier']:.1f})")
        print()
    
    print("\n" + "=" * 100)
    print("SECTION 3: SIMULATED SAMPLE ANALYSIS (What actually happens in the simulation)")
    print("=" * 100)
    
    print(f"\nRunning {iterations} Monte Carlo iterations to capture the input distribution...")
    
    # Manually run a subset of iterations to capture what's being fed into DCF
    np.random.seed(42)  # For reproducibility
    
    simulated_inputs = {
        'scenario': [],
        'growth': [],
        'terminal_growth': [],
        'wacc': [],
    }
    
    for _ in range(iterations):
        # Sample scenario (same logic as simulate_value)
        scenario_name = np.random.choice(
            list(scenarios.keys()),
            p=[s['probability'] for s in scenarios.values()]
        )
        scenario = scenarios[scenario_name]
        
        # Calculate scenario-specific parameters
        scenario_growth = constrained_growth * scenario['growth_multiplier']
        sim_growth = np.random.normal(loc=scenario_growth, scale=0.03)  # ±3% noise
        sim_growth = np.clip(sim_growth, -0.30, 0.50)
        
        scenario_terminal = terminal_growth * scenario['terminal_multiplier']
        sim_term_growth = np.clip(scenario_terminal, 0.015, 0.035)
        
        sim_wacc = np.random.normal(loc=wacc, scale=0.01)
        sim_wacc = max(sim_wacc, 0.03)
        
        simulated_inputs['scenario'].append(scenario_name)
        simulated_inputs['growth'].append(sim_growth)
        simulated_inputs['terminal_growth'].append(sim_term_growth)
        simulated_inputs['wacc'].append(sim_wacc)
    
    df = pd.DataFrame(simulated_inputs)
    
    print(f"\n📈 Distribution of Simulated Inputs:")
    print(f"\n   Scenario Sampling:")
    scenario_counts = df['scenario'].value_counts()
    for scenario, count in scenario_counts.items():
        print(f"      {scenario.capitalize()}: {count} iterations ({count/iterations*100:.1f}%)")
    
    print(f"\n   Growth Rate Distribution:")
    print(f"      Min:    {df['growth'].min()*100:.2f}%")
    print(f"      25th:   {df['growth'].quantile(0.25)*100:.2f}%")
    print(f"      Median: {df['growth'].median()*100:.2f}%")
    print(f"      75th:   {df['growth'].quantile(0.75)*100:.2f}%")
    print(f"      Max:    {df['growth'].max()*100:.2f}%")
    print(f"      Mean:   {df['growth'].mean()*100:.2f}%")
    print(f"      Std:    {df['growth'].std()*100:.2f}%")
    
    print(f"\n   Terminal Growth Distribution:")
    print(f"      Min:    {df['terminal_growth'].min()*100:.2f}%")
    print(f"      Median: {df['terminal_growth'].median()*100:.2f}%")
    print(f"      Max:    {df['terminal_growth'].max()*100:.2f}%")
    
    print(f"\n   WACC Distribution:")
    print(f"      Min:    {df['wacc'].min()*100:.2f}%")
    print(f"      Median: {df['wacc'].median()*100:.2f}%")
    print(f"      Max:    {df['wacc'].max()*100:.2f}%")
    
    print("\n" + "=" * 100)
    print("SECTION 4: CRITICAL ANALYSIS - GARBAGE IN, GARBAGE OUT?")
    print("=" * 100)
    
    print("\n🔍 Evaluating Assumption Quality:\n")
    
    # Check 1: Is analyst growth rate realistic?
    print("   ✓ CHECK 1: Analyst Growth Rate Sanity")
    if analyst_growth > 0.30:
        print(f"      ⚠️  WARNING: Analyst expects {analyst_growth*100:.1f}% growth - very optimistic!")
        print(f"          This exceeds typical sustainable growth for {sector} sector.")
    elif analyst_growth > 0.20:
        print(f"      ⚠️  CAUTION: Analyst expects {analyst_growth*100:.1f}% growth - above average")
    else:
        print(f"      ✅ Analyst growth {analyst_growth*100:.1f}% appears reasonable")
    
    # Check 2: Does the sector constraint help?
    print(f"\n   ✓ CHECK 2: Sector Constraint Effectiveness")
    if constrained_growth < analyst_growth:
        reduction = (analyst_growth - constrained_growth) * 100
        print(f"      ✅ Sector constraint reduced growth by {reduction:.1f}pp")
        print(f"         ({analyst_growth*100:.1f}% → {constrained_growth*100:.1f}%)")
    else:
        print(f"      ℹ️  No constraint applied (analyst within sector limits)")
    
    # Check 3: Are scenarios realistic?
    print(f"\n   ✓ CHECK 3: Scenario Range Analysis")
    bear_growth = df[df['scenario'] == 'bear']['growth'].mean()
    bull_growth = df[df['scenario'] == 'bull']['growth'].mean()
    scenario_range = (bull_growth - bear_growth) * 100
    
    print(f"      Bear scenario avg: {bear_growth*100:.1f}%")
    print(f"      Bull scenario avg: {bull_growth*100:.1f}%")
    print(f"      Range: {scenario_range:.1f}pp")
    
    if scenario_range < 5:
        print(f"      ⚠️  WARNING: Scenario range is narrow ({scenario_range:.1f}pp)")
        print(f"          Monte Carlo may show false precision!")
    elif scenario_range > 20:
        print(f"      ⚠️  WARNING: Scenario range is very wide ({scenario_range:.1f}pp)")
        print(f"          Results may be too uncertain to be actionable")
    else:
        print(f"      ✅ Scenario range appears reasonable")
    
    # Check 4: Terminal value concern
    print(f"\n   ✓ CHECK 4: Terminal Value Dominance Check")
    print(f"      Running a sample DCF to check terminal value %...")
    
    terminal_pct = None
    try:
        # Run full DCF with terminal value calculation
        pv_explicit, term_pv, pv_term, ev, terminal_method_used = engine.calculate_dcf(
            data.fcf, constrained_growth, terminal_growth, wacc, 
            years=5, terminal_method=terminal_method
        )
        
        # Calculate terminal %
        terminal_pct = (pv_term / ev * 100) if ev > 0 else None
        
        if terminal_pct:
            print(f"      Terminal Value: {terminal_pct:.1f}% of enterprise value")
            
            if terminal_pct > 70:
                print(f"      ⚠️  WARNING: Terminal value dominates the valuation!")
                print(f"          Fair value is mostly driven by perpetuity assumptions")
                print(f"          Small changes in terminal growth can swing valuation ±30%")
            elif terminal_pct > 60:
                print(f"      ⚠️  CAUTION: Terminal value is significant but controlled")
            else:
                print(f"      ✅ Terminal value is reasonable")
    except Exception as e:
        print(f"      ⚠️  Could not calculate terminal value %: {e}")
    
    # Check 5: Historical validation (if we had historical data)
    print(f"\n   ✓ CHECK 5: Reality Check Against Company History")
    if data.revenue:
        print(f"      Current Revenue: ${data.revenue:,.0f}M")
        implied_rev_5y = data.revenue * (1 + constrained_growth)**5
        print(f"      Implied Revenue in 5Y: ${implied_rev_5y:,.0f}M")
        print(f"      Revenue CAGR required: {constrained_growth*100:.1f}%")
        print(f"      ")
        print(f"      ℹ️  RECOMMENDATION: Compare to historical 5Y revenue CAGR")
        print(f"         If historical < {constrained_growth*100:.1f}%, current assumptions may be optimistic")
    
    print("\n" + "=" * 100)
    print("SECTION 5: RECOMMENDATIONS")
    print("=" * 100)
    
    print("\n💡 Based on this analysis:\n")
    
    # Determine if GIGO is happening
    issues_found = []
    
    if analyst_growth > 0.30:
        issues_found.append("Analyst growth rate is extremely high")
    
    if scenario_range < 5:
        issues_found.append("Scenario range is too narrow (false precision)")
    
    if terminal_pct and terminal_pct > 70:
        issues_found.append("Terminal value dominates (>70% of valuation)")
    
    if issues_found:
        print("   ⚠️  POTENTIAL GARBAGE IN, GARBAGE OUT ISSUES:\n")
        for i, issue in enumerate(issues_found, 1):
            print(f"      {i}. {issue}")
        
        print("\n   🔧 SUGGESTED FIXES:\n")
        if "Analyst growth" in issues_found[0] if issues_found else "":
            print("      • Further constrain analyst growth rate")
            print("        Consider using historical revenue CAGR as upper bound")
        
        if any("narrow" in issue for issue in issues_found):
            print("      • Widen scenario multipliers (e.g., Bear 0.3x, Bull 1.5x)")
            print("        This will increase uncertainty and reduce false confidence")
        
        if any("Terminal" in issue for issue in issues_found):
            print("      • Reduce forecast period from 5 to 3 years")
            print("        OR increase terminal value cap from 65% to 60%")
    else:
        print("   ✅ Monte Carlo assumptions appear reasonable!")
        print("      The scenario-based approach with sector constraints")
        print("      provides a realistic distribution of possible outcomes.")
    
    print("\n" + "=" * 100)
    print("ANALYSIS COMPLETE")
    print("=" * 100 + "\n")
    
    return df


if __name__ == "__main__":
    # Analyze JNJ in detail
    df = analyze_monte_carlo_inputs("JNJ", iterations=5000)
    
    print("\n📊 You can now examine the simulated inputs DataFrame:")
    print("   - df['scenario'].value_counts() - scenario distribution")
    print("   - df['growth'].describe() - growth rate statistics")
    print("   - df.plot.hist() - visualize distributions")
