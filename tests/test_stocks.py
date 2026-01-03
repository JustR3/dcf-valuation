#!/usr/bin/env python3
"""
Stock Valuation Test with Mid-Cap S&P 500 Companies

Tests DCF valuation engine with less popular stocks to ensure
all integrations (FRED, Shiller, Damodaran) work correctly.

Mid-cap stocks selected (not mega-cap like AAPL, MSFT, GOOGL):
- APA: APA Corporation (Energy)
- CF: CF Industries (Basic Materials)
- JKHY: Jack Henry & Associates (Technology/Fintech)
- LKQ: LKQ Corporation (Consumer Cyclical)
- SNA: Snap-on Inc. (Industrials)

Run with: uv run python test_stocks.py
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

print("\n" + "=" * 80)
print("MID-CAP S&P 500 STOCK VALUATION TEST")
print("=" * 80 + "\n")

# Load environment
import src.env_loader as env_loader

# Check API key
fred_key = os.getenv("FRED_API_KEY")
if not fred_key or fred_key == "your_fred_api_key_here":
    print("⚠️  WARNING: FRED_API_KEY not configured")
    print("   Risk-free rate will use fallback value of 4.0%")
    print()
    print("   To fix this:")
    print("   1. Get free API key at: https://fred.stlouisfed.org/docs/api/api_key.html")
    print("   2. Open config/secrets.env")
    print("   3. Replace 'your_fred_api_key_here' with your actual API key")
    print()

# Test stocks (mid-cap S&P 500 companies)
test_stocks = {
    "APA": "APA Corporation (Energy)",
    "CF": "CF Industries (Basic Materials)", 
    "JKHY": "Jack Henry & Associates (Technology/Fintech)",
    "LKQ": "LKQ Corporation (Consumer Cyclical)",
    "SNA": "Snap-on Inc. (Industrials)"
}

print(f"Testing {len(test_stocks)} mid-cap S&P 500 stocks:")
for ticker, name in test_stocks.items():
    print(f"   • {ticker}: {name}")
print()

# Import DCF components
try:
    from src.dcf_engine import DCFEngine
    from src.external.fred import get_fred_connector
    from src.external.shiller import get_equity_risk_scalar
    from src.external.damodaran import get_damodaran_loader
    
    print("✅ All modules imported successfully")
    print()
    
except Exception as e:
    print(f"❌ Failed to import modules: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Get external data
print("-" * 80)
print("Fetching External Market Data")
print("-" * 80)

try:
    # FRED data
    fred = get_fred_connector()
    macro_data = fred.get_macro_data()
    print(f"✅ FRED: Risk-free rate = {macro_data.risk_free_rate:.2%} (Source: {macro_data.source})")
    
    # Shiller CAPE
    cape_data = get_equity_risk_scalar()
    print(f"✅ Shiller CAPE: {cape_data['current_cape']:.2f} (State: {cape_data['regime']}, Scalar: {cape_data['risk_scalar']:.2f}x)")
    
    # Damodaran
    damodaran = get_damodaran_loader()
    print(f"✅ Damodaran: Sector priors loaded")
    
    print()
    
except Exception as e:
    print(f"❌ Failed to fetch external data: {e}")
    import traceback
    traceback.print_exc()
    print()

# Run valuations
print("-" * 80)
print("Running DCF Valuations")
print("-" * 80)
print()

results = {}

for ticker, name in test_stocks.items():
    print(f"📊 Valuing {ticker} ({name})")
    print("   " + "-" * 76)
    
    try:
        # Initialize DCF engine
        engine = DCFEngine(ticker=ticker, auto_fetch=True)
        
        if not engine.is_ready:
            print(f"   ❌ Failed to fetch data: {engine.last_error}")
            print()
            continue
        
        # Get company data
        data = engine.company_data
        sector = data.sector if data.sector else 'Unknown'
        
        print(f"   • Sector: {sector}")
        print(f"   • Market Cap: ${data.market_cap:.2f}B")
        print(f"   • Current Price: ${data.current_price:.2f}")
        print(f"   • Beta: {data.beta:.2f}")
        
        # Get Damodaran priors for this sector
        if sector != 'Unknown':
            priors = damodaran.get_sector_priors(sector)
            print(f"   • Damodaran Beta: {priors.beta:.2f}")
            if priors.operating_margin:
                print(f"   • Expected Op. Margin: {priors.operating_margin:.1%}")
        
        # Run DCF valuation with Monte Carlo simulation
        print(f"   Running Monte Carlo simulation...")
        mc_result = engine.simulate_value(
            iterations=1000,  # Reduced for faster testing
            growth=None,  # Use analyst estimates
            term_growth=0.025,
            wacc=None,  # Calculate automatically
            years=5
        )
        
        # Display results
        current_price = data.current_price
        fair_value = mc_result['median_value']
        mean_value = mc_result['mean_value']
        upside = ((fair_value - current_price) / current_price * 100) if current_price > 0 else 0
        prob_undervalued = mc_result['prob_undervalued']
        
        print()
        print(f"   ✅ Valuation Complete:")
        print(f"      Current Price:    ${current_price:.2f}")
        print(f"      Fair Value (Med): ${fair_value:.2f}")
        print(f"      Fair Value (Avg): ${mean_value:.2f}")
        print(f"      Upside:           {upside:+.1f}%")
        print(f"      P(Undervalued):   {prob_undervalued:.1f}%")
        print(f"      Assessment:       {mc_result['assessment']}")
        
        # Conviction rating
        if upside > 15 and prob_undervalued > 75:
            conviction = "HIGH"
        elif upside > 10 and prob_undervalued > 60:
            conviction = "MODERATE"
        else:
            conviction = "LOW"
        
        print(f"      Conviction:       {conviction}")
        print()
        
        results[ticker] = {
            'name': name,
            'sector': sector,
            'current_price': current_price,
            'fair_value': fair_value,
            'upside': upside,
            'probability': prob_undervalued,
            'conviction': conviction
        }
        
    except Exception as e:
        print(f"   ❌ Valuation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        print()
        continue

# Summary
print("=" * 80)
print("VALUATION SUMMARY")
print("=" * 80)
print()

if results:
    print(f"Successfully valued {len(results)}/{len(test_stocks)} stocks:")
    print()
    
    # Sort by upside
    sorted_results = sorted(results.items(), key=lambda x: x[1]['upside'], reverse=True)
    
    for ticker, data in sorted_results:
        print(f"{ticker:6s} | ${data['current_price']:8.2f} → ${data['fair_value']:8.2f} | "
              f"{data['upside']:+6.1f}% | {data['probability']:5.1f}% prob | "
              f"{data['conviction']:8s} | {data['sector']}")
    
    print()
    print("Legend:")
    print("  Current → Fair Value | Upside % | Probability of undervaluation | Conviction | Sector")
    print()
    
else:
    print("⚠️  No stocks were successfully valued.")
    print("   Check error messages above for details.")
    print()

print("=" * 80)
print()
