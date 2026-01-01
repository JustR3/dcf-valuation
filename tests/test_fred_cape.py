"""
Quick test of FRED and Shiller CAPE integrations.

This script tests the newly integrated external data sources:
1. FRED API for risk-free rate
2. True Shiller CAPE from Yale dataset
3. DCF engine integration

Run: python test_fred_cape.py
"""

import sys
sys.path.insert(0, '/Users/justra/Python/dcf-valuation')

# Load environment variables
import src.env_loader

print("="*80)
print("TESTING FRED & SHILLER CAPE INTEGRATION")
print("="*80)
print()

# Test 1: FRED Connector
print("1️⃣  Testing FRED API Connection...")
print("-" * 80)
try:
    from src.pipeline.external.fred import get_fred_connector
    
    fred = get_fred_connector()
    macro_data = fred.get_macro_data()
    
    print(f"✅ FRED API Working!")
    print(f"   Source: {macro_data.source}")
    print(f"   Risk-free rate (10Y Treasury): {macro_data.risk_free_rate:.4f} ({macro_data.risk_free_rate*100:.2f}%)")
    if macro_data.inflation_rate:
        print(f"   Inflation (CPI YoY): {macro_data.inflation_rate:.4f} ({macro_data.inflation_rate*100:.2f}%)")
    if macro_data.gdp_growth:
        print(f"   GDP Growth (annualized): {macro_data.gdp_growth:.4f} ({macro_data.gdp_growth*100:.2f}%)")
    print(f"   Fetched at: {macro_data.fetched_at}")
    print()
except Exception as e:
    print(f"❌ FRED API Error: {e}")
    print()

# Test 2: Shiller CAPE
print("2️⃣  Testing Shiller CAPE Integration...")
print("-" * 80)
try:
    from src.pipeline.external.shiller import get_current_cape, get_equity_risk_scalar, display_cape_summary
    
    # Get current CAPE
    current_cape = get_current_cape()
    print(f"✅ Shiller CAPE Working!")
    print(f"   Current CAPE: {current_cape:.2f}")
    
    # Get risk scalar
    print()
    print("   Equity Risk Adjustment:")
    cape_data = get_equity_risk_scalar()
    display_cape_summary(cape_data)
    print()
    
except Exception as e:
    print(f"❌ Shiller CAPE Error: {e}")
    print()

# Test 3: DCF Engine Integration
print("3️⃣  Testing DCF Engine Integration...")
print("-" * 80)
try:
    from src.dcf_engine import DCFEngine
    
    # Create engine for AAPL (example)
    engine = DCFEngine("AAPL")
    
    # Test WACC with both FRED and Shiller
    wacc_breakdown = engine.get_wacc_breakdown(
        use_dynamic_rf=True,
        use_cape_adjustment=True
    )
    
    print(f"✅ DCF Engine Integration Working!")
    print()
    print("   WACC Breakdown:")
    print(f"   ├─ Risk-free rate: {wacc_breakdown['risk_free_rate']*100:.2f}%")
    print(f"   │  Source: {wacc_breakdown['rf_source']}")
    print(f"   ├─ Beta: {wacc_breakdown['beta']:.2f}")
    print(f"   ├─ Equity Risk Premium: {wacc_breakdown['equity_risk_premium']*100:.2f}%")
    print(f"   ├─ Base WACC: {wacc_breakdown['base_wacc']*100:.2f}%")
    
    if wacc_breakdown.get('cape_info'):
        print(f"   ├─ CAPE Adjustment: {wacc_breakdown['cape_adjustment']*10000:.0f} bps")
        print(f"   │  CAPE Ratio: {wacc_breakdown['cape_info']['cape_ratio']:.2f} ({wacc_breakdown['cape_info']['market_state']})")
        print(f"   │  Risk Scalar: {wacc_breakdown['cape_info']['risk_scalar']:.2f}x")
        if wacc_breakdown['cape_info'].get('percentile'):
            print(f"   │  Historical Percentile: {wacc_breakdown['cape_info']['percentile']:.1f}%")
    
    print(f"   └─ Final WACC: {wacc_breakdown['final_wacc']*100:.2f}%")
    print()
    
    # Compare to static baseline
    wacc_static = engine.get_wacc_breakdown(
        use_dynamic_rf=False,
        use_cape_adjustment=False
    )
    
    diff_bps = (wacc_breakdown['final_wacc'] - wacc_static['final_wacc']) * 10000
    print(f"   📊 Comparison vs Static (config):")
    print(f"   └─ Difference: {diff_bps:+.0f} basis points")
    print()
    
except Exception as e:
    print(f"❌ DCF Engine Error: {e}")
    import traceback
    traceback.print_exc()
    print()

print("="*80)
print("TEST COMPLETE")
print("="*80)
print()
print("ℹ️  Setup Instructions:")
print("   1. Create config/secrets.env from config/secrets.env.example")
print("   2. Add FRED_API_KEY (get free key at https://fred.stlouisfed.org)")
print("   3. Install dependencies: pip install fredapi requests openpyxl")
print()
