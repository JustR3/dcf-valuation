#!/usr/bin/env python3
"""
Comprehensive Integration Test for External APIs
Tests FRED, Shiller CAPE, and Damodaran integrations

Run with: python test_integrations.py
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("\n" + "=" * 80)
print("EXTERNAL DATA INTEGRATION TEST - FRED + SHILLER + DAMODARAN")
print("=" * 80 + "\n")

# =============================================================================
# Environment Setup Check
# =============================================================================

print("🔧 Environment Setup Check")
print("-" * 80)

# Load environment variables
try:
    import src.env_loader as env_loader
    
    if env_loader.is_environment_loaded():
        print("✅ Environment variables loaded from config/secrets.env")
    else:
        print("⚠️  Failed to load environment variables")
        print("   Make sure config/secrets.env exists and has valid API keys")
    
    # Check for FRED API key
    fred_key = os.getenv("FRED_API_KEY")
    if fred_key and fred_key != "your_fred_api_key_here":
        print(f"✅ FRED_API_KEY found: {fred_key[:8]}...{fred_key[-4:]}")
    else:
        print("⚠️  FRED_API_KEY not set or is placeholder")
        print("   Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        print("   Set it in config/secrets.env")
    
    print()

except Exception as e:
    print(f"❌ Environment setup failed: {str(e)}\n")
    sys.exit(1)

# =============================================================================
# Test 1: FRED API (Risk-Free Rate, Inflation, GDP)
# =============================================================================

print("📊 Test 1: FRED API Integration")
print("-" * 80)

try:
    from src.external.fred import get_fred_connector
    
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
    print(f"❌ FRED API Test Failed: {str(e)}")
    import traceback
    traceback.print_exc()
    print()

# =============================================================================
# Test 2: Shiller CAPE (Market Valuation)
# =============================================================================

print("📊 Test 2: Shiller CAPE Integration")
print("-" * 80)

try:
    from src.external.shiller import get_current_cape, get_equity_risk_scalar
    
    cape = get_current_cape()
    cape_data = get_equity_risk_scalar()
    
    print(f"✅ Shiller CAPE Data: Successfully fetched")
    print(f"   Current CAPE Ratio: {cape:.2f}")
    print(f"   Market State: {cape_data['regime']}")
    print(f"   Historical Percentile: {cape_data.get('percentile', 0):.1f}%")
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
    
except Exception as e:
    print(f"❌ Shiller CAPE Test Failed: {str(e)}")
    import traceback
    traceback.print_exc()
    print()

# =============================================================================
# Test 3: Damodaran Sector Priors (Academic Data)
# =============================================================================

print("📊 Test 3: Damodaran Sector Priors Integration")
print("-" * 80)

try:
    from src.external.damodaran import get_damodaran_loader
    
    loader = get_damodaran_loader()
    
    # Test specific sectors
    test_sectors = ["Technology", "Healthcare", "Energy", "Financial Services"]
    
    print("✅ Damodaran Loader: Initialized")
    print("   Testing sector priors:\n")
    
    for sector in test_sectors:
        priors = loader.get_sector_priors(sector)
        print(f"   {sector}:")
        if priors.beta:
            print(f"      Beta: {priors.beta:.2f}")
        if priors.unlevered_beta:
            print(f"      Unlevered Beta: {priors.unlevered_beta:.2f}")
        if priors.operating_margin:
            print(f"      Operating Margin: {priors.operating_margin:.2%}")
        if priors.revenue_growth:
            print(f"      Revenue Growth: {priors.revenue_growth:.2%}")
        print()
    
except Exception as e:
    print(f"❌ Damodaran Test Failed: {str(e)}")
    import traceback
    traceback.print_exc()
    print()

# =============================================================================
# Summary
# =============================================================================

print("=" * 80)
print("TEST SUMMARY")
print("=" * 80)
print()
print("All external data integrations tested.")
print("If you see warnings above, follow the instructions to fix them.")
print()
print("Next Steps:")
print("1. If FRED_API_KEY is missing, get free key at: https://fred.stlouisfed.org/")
print("2. Run a stock valuation test: python test_integrations.py --stock")
print()
