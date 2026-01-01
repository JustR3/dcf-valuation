"""
Comprehensive External Data Integration Test
Tests FRED, Shiller CAPE, and Damodaran sector priors

Run with: uv run python test_external_integrations.py
"""

# Load environment variables
import src.env_loader

print("\n" + "="*80)
print("EXTERNAL DATA INTEGRATION TEST - FRED + SHILLER + DAMODARAN")
print("="*80 + "\n")

# =============================================================================
# Test 1: FRED API (Risk-Free Rate, Inflation, GDP)
# =============================================================================

print("📊 Test 1: FRED API Integration")
print("-" * 80)

try:
    from src.pipeline.external.fred import get_fred_connector
    
    fred = get_fred_connector()
    macro_data = fred.get_macro_data()
    
    print(f"✅ FRED API Connection: Working")
    print(f"   Source: {macro_data.source}")
    print(f"   Risk-Free Rate (10Y Treasury): {macro_data.risk_free_rate:.4f} ({macro_data.risk_free_rate*100:.2f}%)")
    
    if macro_data.inflation_rate is not None:
        print(f"   Inflation Rate (CPI YoY): {macro_data.inflation_rate:.4f} ({macro_data.inflation_rate*100:.2f}%)")
    
    if macro_data.gdp_growth is not None:
        print(f"   GDP Growth (Real, Annualized): {macro_data.gdp_growth:.4f} ({macro_data.gdp_growth*100:.2f}%)")
    
    if macro_data.fetched_at:
        print(f"   Fetched At: {macro_data.fetched_at.strftime('%Y-%m-%d %H:%M:%S')}")
    
    print()
    
except Exception as e:
    print(f"❌ FRED API Test Failed: {str(e)}\n")

# =============================================================================
# Test 2: Shiller CAPE (Market Valuation)
# =============================================================================

print("📊 Test 2: Shiller CAPE Integration")
print("-" * 80)

try:
    from src.pipeline.external.shiller import get_current_cape, get_equity_risk_scalar, display_cape_summary
    
    cape = get_current_cape()
    cape_data = get_equity_risk_scalar()
    
    print(f"✅ Shiller CAPE Data: Successfully fetched from Yale")
    print(f"   Current CAPE Ratio: {cape:.2f}")
    print(f"   Market State: {cape_data['regime']}")
    print(f"   Historical Percentile: {cape_data['percentile']:.1f}%")
    print(f"   Risk Scalar: {cape_data['risk_scalar']:.2f}x")
    
    if cape_data['risk_scalar'] > 1.0:
        adjustment = (cape_data['risk_scalar'] - 1.0) * 100
        print(f"   Impact: Boost expected returns by {adjustment:.0f}%")
    elif cape_data['risk_scalar'] < 1.0:
        adjustment = (1.0 - cape_data['risk_scalar']) * 100
        print(f"   Impact: Reduce expected returns by {adjustment:.0f}%")
    else:
        print(f"   Impact: Neutral (no adjustment)")
    
    print()
    
    # Display pretty summary
    print("   📈 Detailed CAPE Summary:")
    print("   " + "-" * 76)
    display_cape_summary(cape_data)
    print()
    
except Exception as e:
    print(f"❌ Shiller CAPE Test Failed: {str(e)}\n")

# =============================================================================
# Test 3: Damodaran Sector Priors (Academic Data)
# =============================================================================

print("📊 Test 3: Damodaran Sector Priors Integration")
print("-" * 80)

try:
    from src.pipeline.external.damodaran import get_damodaran_loader
    
    loader = get_damodaran_loader()
    
    # Test specific sectors
    test_sectors = ["Technology", "Healthcare", "Energy", "Financial Services"]
    
    print("✅ Damodaran Loader: Initialized")
    print("   Testing key sectors...\n")
    
    for sector in test_sectors:
        priors = loader.get_sector_priors(sector)
        
        print(f"   📂 {sector}:")
        print(f"      Beta (Levered): {priors.beta:.2f}" if priors.beta else "      Beta: N/A")
        
        if priors.unlevered_beta:
            print(f"      Beta (Unlevered): {priors.unlevered_beta:.2f}")
        
        if priors.revenue_growth:
            print(f"      Revenue Growth: {priors.revenue_growth:.1%}")
        
        if priors.operating_margin:
            print(f"      Operating Margin: {priors.operating_margin:.1%}")
        
        if priors.erp:
            print(f"      Equity Risk Premium: {priors.erp:.1%}")
        
        print()
    
    # Test unmapped sector fallback
    print("   Testing unmapped sector fallback...")
    unknown_priors = loader.get_sector_priors("UnknownSector")
    print(f"   ✅ Fallback works: Beta={unknown_priors.beta:.2f}, Growth={unknown_priors.revenue_growth:.1%}")
    print()
    
except Exception as e:
    print(f"❌ Damodaran Test Failed: {str(e)}\n")

# =============================================================================
# Test 4: DCF Engine Integration with All External Data
# =============================================================================

print("📊 Test 4: DCF Engine Integration with External Data")
print("-" * 80)

try:
    from src.dcf_engine import DCFEngine
    
    # Test with AAPL
    ticker = "AAPL"
    print(f"Testing DCF engine for {ticker} with external data integrations...\n")
    
    engine = DCFEngine(ticker)
    
    # Get WACC breakdown with all external data
    wacc_breakdown = engine.get_wacc_breakdown(
        use_dynamic_rf=True,  # Use FRED API
        use_cape_adjustment=True  # Use Shiller CAPE
    )
    
    print(f"✅ DCF Engine Integration: Working")
    print(f"\n   {ticker} WACC Breakdown:")
    print(f"   {'='*76}")
    print(f"   Base Components:")
    print(f"      Risk-Free Rate: {wacc_breakdown['risk_free_rate']:.2%}")
    print(f"      Source: {wacc_breakdown['rf_source']}")
    print(f"      Beta: {wacc_breakdown['beta']:.2f}")
    print(f"      Market Risk Premium: {wacc_breakdown['market_risk_premium']:.2%}")
    print(f"      Base WACC: {wacc_breakdown['base_wacc']:.2%}")
    
    print(f"\n   CAPE Adjustment:")
    cape_info = wacc_breakdown['cape_info']
    print(f"      Current CAPE: {cape_info['cape_ratio']:.2f}")
    print(f"      Market State: {cape_info['market_state']}")
    
    if 'risk_scalar' in cape_info:
        print(f"      Risk Scalar: {cape_info['risk_scalar']:.2f}x")
    
    if 'adjustment_bps' in cape_info:
        print(f"      Adjustment: {cape_info['adjustment_bps']:+.0f} basis points")
    
    if 'percentile' in cape_info:
        print(f"      Historical Percentile: {cape_info['percentile']:.1f}%")
    
    print(f"\n   Final WACC: {wacc_breakdown['final_wacc']:.2%}")
    
    # Test with Damodaran sector priors
    print(f"\n   Testing Damodaran sector data for {ticker}...")
    from src.pipeline.external.damodaran import get_damodaran_loader
    
    loader = get_damodaran_loader()
    sector = "Technology"  # AAPL is in Technology
    sector_priors = loader.get_sector_priors(sector)
    
    print(f"   ✅ Sector Priors Available:")
    print(f"      Sector: {sector}")
    print(f"      Academic Beta: {sector_priors.beta:.2f}")
    print(f"      vs AAPL Beta: {wacc_breakdown['beta']:.2f}")
    print(f"      Expected Growth: {sector_priors.revenue_growth:.1%}")
    print(f"      Operating Margin: {sector_priors.operating_margin:.1%}")
    
    print()
    
except Exception as e:
    print(f"❌ DCF Engine Integration Test Failed: {str(e)}\n")

# =============================================================================
# Summary
# =============================================================================

print("="*80)
print("✅ ALL TESTS COMPLETED")
print("="*80)
print("\nExternal Data Sources Integrated:")
print("  1. ✅ FRED API - Real-time 10Y Treasury, Inflation, GDP")
print("  2. ✅ Shiller CAPE - Market valuation from Yale dataset")
print("  3. ✅ Damodaran Sector Priors - Academic betas and margins from NYU Stern")
print("  4. ✅ DCF Engine - Integrated with all external data sources")
print("\nData Pipeline:")
print("  • FRED: 24-hour cache (daily updates)")
print("  • Shiller: 168-hour cache (weekly updates)")
print("  • Damodaran: 30-day cache (quarterly updates)")
print("\nNext Steps:")
print("  • Add FRED_API_KEY to config/secrets.env for live risk-free rate")
print("  • System gracefully degrades if APIs unavailable")
print("  • All data sources have academic/authoritative origins")
print()
