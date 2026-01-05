"""
Historical validation for JNJ growth assumptions.

Fetches actual historical revenue data to validate whether 11.3% growth is realistic.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def analyze_historical_growth(ticker: str = "JNJ", years: int = 5):
    """
    Fetch and analyze historical revenue growth to validate DCF assumptions.
    
    Args:
        ticker: Stock ticker symbol
        years: Number of years to look back
    """
    print("=" * 100)
    print(f"HISTORICAL GROWTH VALIDATION: {ticker}")
    print("=" * 100)
    
    # Fetch company data
    stock = yf.Ticker(ticker)
    info = stock.info
    
    print(f"\n📊 Company: {info.get('longName', ticker)}")
    print(f"   Sector: {info.get('sector', 'N/A')}")
    print(f"   Industry: {info.get('industry', 'N/A')}")
    
    # Get analyst estimate for comparison
    analyst_growth = info.get('revenueGrowth') or info.get('earningsGrowth')
    if analyst_growth:
        print(f"   Analyst Forward Growth: {analyst_growth*100:.1f}%")
    
    print("\n" + "=" * 100)
    print("HISTORICAL REVENUE ANALYSIS")
    print("=" * 100)
    
    # Fetch quarterly financials (more data points)
    try:
        quarterly = stock.quarterly_financials
        if quarterly.empty:
            print("❌ No quarterly financial data available")
            return
        
        # Get Total Revenue row
        if 'Total Revenue' in quarterly.index:
            revenue_row = quarterly.loc['Total Revenue']
        else:
            print("❌ Total Revenue not found in financials")
            print("\nAvailable metrics:")
            print(quarterly.index.tolist())
            return
        
        # Sort by date (oldest first)
        revenue_data = revenue_row.sort_index()
        
        print(f"\n📈 Quarterly Revenue History (Last {len(revenue_data)} quarters):\n")
        print(f"{'Quarter':<12} {'Revenue ($M)':<15} {'YoY Growth %':<15}")
        print("-" * 45)
        
        # Calculate YoY growth for each quarter
        quarterly_growth = []
        for i, (date, rev) in enumerate(revenue_data.items()):
            rev_millions = rev / 1_000_000  # Convert to millions
            
            # Calculate YoY growth (compare to same quarter last year, i.e., 4 quarters ago)
            if i >= 4:
                prev_year_rev = revenue_data.iloc[i-4]
                yoy_growth = (rev - prev_year_rev) / prev_year_rev * 100
                quarterly_growth.append(yoy_growth)
                print(f"{date.strftime('%Y-%m-%d'):<12} ${rev_millions:>12,.0f} {yoy_growth:>13.1f}%")
            else:
                print(f"{date.strftime('%Y-%m-%d'):<12} ${rev_millions:>12,.0f} {'N/A':>13}")
        
        # Calculate statistics
        if quarterly_growth:
            avg_yoy = sum(quarterly_growth) / len(quarterly_growth)
            median_yoy = sorted(quarterly_growth)[len(quarterly_growth)//2]
            latest_yoy = quarterly_growth[-1]
            
            print("\n" + "=" * 100)
            print("GROWTH RATE ANALYSIS")
            print("=" * 100)
            
            print(f"\n📊 Historical YoY Revenue Growth (Quarterly):")
            print(f"   Latest Quarter:  {latest_yoy:>6.1f}%")
            print(f"   Average:         {avg_yoy:>6.1f}%")
            print(f"   Median:          {median_yoy:>6.1f}%")
            print(f"   Min:             {min(quarterly_growth):>6.1f}%")
            print(f"   Max:             {max(quarterly_growth):>6.1f}%")
        
    except Exception as e:
        print(f"❌ Error fetching quarterly data: {e}")
        print("\nTrying annual financials instead...")
    
    # Fetch annual financials as fallback
    try:
        annual = stock.financials
        if annual.empty:
            print("❌ No annual financial data available")
            return
        
        # Get Total Revenue row
        if 'Total Revenue' in annual.index:
            revenue_row = annual.loc['Total Revenue']
        else:
            print("❌ Total Revenue not found in annual financials")
            return
        
        # Sort by date (oldest first)
        revenue_data = revenue_row.sort_index()
        
        print(f"\n📈 Annual Revenue History (Last {len(revenue_data)} years):\n")
        print(f"{'Year':<12} {'Revenue ($M)':<15} {'YoY Growth %':<15}")
        print("-" * 45)
        
        # Calculate YoY growth
        annual_growth = []
        for i, (date, rev) in enumerate(revenue_data.items()):
            rev_millions = rev / 1_000_000
            
            if i > 0:
                prev_rev = revenue_data.iloc[i-1]
                yoy_growth = (rev - prev_rev) / prev_rev * 100
                annual_growth.append(yoy_growth)
                print(f"{date.strftime('%Y'):<12} ${rev_millions:>12,.0f} {yoy_growth:>13.1f}%")
            else:
                print(f"{date.strftime('%Y'):<12} ${rev_millions:>12,.0f} {'N/A':>13}")
        
        # Calculate CAGR over full period
        if len(revenue_data) >= 2:
            oldest_rev = revenue_data.iloc[0]
            latest_rev = revenue_data.iloc[-1]
            num_years = (revenue_data.index[-1] - revenue_data.index[0]).days / 365.25
            
            cagr = ((latest_rev / oldest_rev) ** (1 / num_years) - 1) * 100
            
            print(f"\n{'=' * 100}")
            print("CAGR CALCULATION")
            print("=" * 100)
            
            print(f"\n📊 Historical Revenue CAGR:")
            print(f"   Period:          {revenue_data.index[0].strftime('%Y')} → {revenue_data.index[-1].strftime('%Y')} ({num_years:.1f} years)")
            print(f"   Starting Rev:    ${oldest_rev/1_000_000:,.0f}M")
            print(f"   Ending Rev:      ${latest_rev/1_000_000:,.0f}M")
            print(f"   CAGR:            {cagr:.1f}%")
            
            if annual_growth:
                avg_annual = sum(annual_growth) / len(annual_growth)
                print(f"   Avg YoY Growth:  {avg_annual:.1f}%")
        
        print("\n" + "=" * 100)
        print("VALIDATION AGAINST DCF ASSUMPTIONS")
        print("=" * 100)
        
        if analyst_growth:
            analyst_pct = analyst_growth * 100
            print(f"\n   DCF Analyst Assumption:     {analyst_pct:.1f}%")
            print(f"   Historical CAGR:            {cagr:.1f}%")
            print(f"   Difference:                 {analyst_pct - cagr:+.1f}pp")
            print()
            
            ratio = analyst_pct / cagr if cagr != 0 else float('inf')
            
            if analyst_pct > cagr * 1.5:
                print("   ⚠️  WARNING: Analyst growth exceeds historical by >50%")
                print("      This suggests optimistic assumptions!")
                print(f"      Recommended: Use historical CAGR + 3pp = {cagr + 3:.1f}%")
            elif analyst_pct > cagr * 1.2:
                print("   ⚠️  CAUTION: Analyst growth exceeds historical by 20-50%")
                print("      Assumptions are optimistic but not unreasonable")
                print("      Consider using historical CAGR as base case")
            elif analyst_pct < cagr * 0.8:
                print("   ℹ️  NOTE: Analyst expects slowdown vs historical")
                print("      This may be justified if company is maturing")
            else:
                print("   ✅ Analyst growth is consistent with historical performance")
                print("      Assumptions appear reasonable")
        
    except Exception as e:
        print(f"❌ Error fetching annual data: {e}")
    
    print("\n" + "=" * 100)
    print("ANALYSIS COMPLETE")
    print("=" * 100 + "\n")


if __name__ == "__main__":
    # Analyze JNJ historical growth
    analyze_historical_growth("JNJ")
    
    print("\n💡 TIP: Run for other stocks:")
    print("   analyze_historical_growth('AAPL')")
    print("   analyze_historical_growth('MSFT')")
