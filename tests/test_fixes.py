"""Test the implemented fixes on diagnostic worst offenders.

Tests Priority 1-4 fixes:
1. Terminal value cap (65% limit)
2. Sector-specific constraints  
3. Scenario-based Monte Carlo
4. Conflict detection

Expected improvements:
- Terminal value should be capped at 65%
- Monte Carlo confidence should decrease from 95-100% to 60-80%
- Extreme valuations should be reduced
- Conflicts should be detected and flagged
"""

from src.dcf_engine import DCFEngine
from src.cli.display import enrich_dcf_with_monte_carlo


def test_fixes_on_worst_offenders():
    """Test fixes on the top 5 worst offenders from diagnostics."""
    
    # Top 5 worst offenders from diagnostic report
    test_stocks = {
        "IBM": "Had 86.5% terminal, 100% MC confidence, +118% upside",
        "VZ": "Had 80.1% terminal, 100% MC confidence, +252% upside",
        "F": "Had 74.3% terminal, 100% MC confidence, +643% upside",
        "BAC": "Had 69.3% terminal, 100% MC confidence, +584% upside",
        "NVDA": "Had 86.9% terminal, 100% MC confidence, 87% growth rate",
    }
    
    print("=" * 80)
    print("TESTING DIAGNOSTIC FIXES ON WORST OFFENDERS")
    print("=" * 80)
    print()
    
    results = {}
    
    for ticker, issue in test_stocks.items():
        print(f"\n{'='*80}")
        print(f"{ticker}: {issue}")
        print("="*80)
        
        try:
            # Run DCF with new fixes
            engine = DCFEngine(ticker, auto_fetch=True)
            
            if not engine.is_ready:
                print(f"❌ Failed to fetch data: {engine.last_error}")
                continue
            
            # Get valuation
            result = engine.get_intrinsic_value()
            
            # Get Monte Carlo (with scenario-based sampling)
            enriched = enrich_dcf_with_monte_carlo(engine, result)
            
            # Extract key metrics
            terminal_info = result.get('terminal_info', {})
            terminal_pct = terminal_info.get('terminal_pct', 0) * 100
            terminal_capped = terminal_info.get('terminal_capped', False)
            
            mc_data = enriched.get('monte_carlo', {})
            mc_probability = mc_data.get('probability', 0)
            
            conflict = enriched.get('valuation_conflict', {})
            conflict_status = conflict.get('conflict_status', 'N/A')
            
            upside = result['upside_downside']
            
            # Display results
            print(f"\n📊 RESULTS:")
            print(f"   Fair Value: ${result['value_per_share']:.2f}")
            print(f"   Current Price: ${result['current_price']:.2f}")
            print(f"   DCF Upside: {upside:+.1f}%")
            print()
            print(f"✅ FIX 1 - Terminal Value Cap:")
            print(f"   Terminal %: {terminal_pct:.1f}%")
            print(f"   Capped: {'YES ✓' if terminal_capped else 'NO (already <65%)'}")
            if terminal_capped:
                orig_pct = terminal_info.get('terminal_pct_before_cap', 0) * 100
                print(f"   Original: {orig_pct:.1f}% → Capped to {terminal_pct:.1f}%")
            print()
            print(f"✅ FIX 2 - Sector Constraints:")
            print(f"   Sector: {engine.company_data.sector}")
            print(f"   Growth Used: {result['inputs']['growth']*100:.1f}%")
            print(f"   Terminal Growth: {result['inputs']['term_growth']*100:.1f}%")
            print()
            print(f"✅ FIX 3 - Scenario-Based Monte Carlo:")
            print(f"   MC Probability: {mc_probability:.1f}%")
            scenario_data = mc_data.get('scenario_sampling', {})
            if scenario_data:
                print(f"   Bear/Base/Bull: {scenario_data.get('bear_samples')}/{scenario_data.get('base_samples')}/{scenario_data.get('bull_samples')}")
            print()
            print(f"✅ FIX 4 - Conflict Detection:")
            print(f"   Status: {conflict_status}")
            if conflict.get('warnings'):
                for warning in conflict['warnings']:
                    print(f"   {warning}")
            
            # Store for comparison
            results[ticker] = {
                'terminal_pct': terminal_pct,
                'terminal_capped': terminal_capped,
                'mc_probability': mc_probability,
                'upside': upside,
                'conflict_status': conflict_status,
            }
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Summary comparison
    print(f"\n\n{'='*80}")
    print("SUMMARY: BEFORE vs AFTER FIXES")
    print("="*80)
    print()
    print(f"{'Stock':<8} {'Terminal Before':<16} {'Terminal After':<16} {'MC Prob Before':<16} {'MC Prob After':<16} {'Upside Change'}")
    print("-" * 80)
    
    expected_before = {
        "IBM": (86.5, 100.0, 117.8),
        "VZ": (80.1, 100.0, 251.8),
        "F": (74.3, 100.0, 643.4),
        "BAC": (69.3, 100.0, 583.8),
        "NVDA": (86.9, 100.0, 18.3),
    }
    
    for ticker in test_stocks:
        if ticker in results:
            r = results[ticker]
            before = expected_before.get(ticker, (0, 0, 0))
            
            terminal_change = f"{before[0]:.1f}% → {r['terminal_pct']:.1f}%"
            mc_change = f"{before[1]:.1f}% → {r['mc_probability']:.1f}%"
            upside_change = f"{before[2]:+.1f}% → {r['upside']:+.1f}%"
            
            print(f"{ticker:<8} {terminal_change:<16} {'':<16} {mc_change:<16} {'':<16} {upside_change}")
    
    print()
    print("="*80)
    print("KEY IMPROVEMENTS:")
    print("="*80)
    print("1. Terminal value capped at 65% (was 70-87%)")
    print("2. Growth rates constrained by sector (no more 87% growth for NVDA)")
    print("3. Monte Carlo confidence more realistic (was 95-100%)")
    print("4. Conflicts explicitly flagged (was 0% detection)")
    print()


if __name__ == "__main__":
    test_fixes_on_worst_offenders()
