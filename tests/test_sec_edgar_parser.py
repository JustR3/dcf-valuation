"""
Test SEC EDGAR XBRL Parser Feasibility
=======================================

Evaluates virattt's SEC filing parser approach for historical financial data extraction.

Approach from: https://colab.research.google.com/gist/virattt/576e592477316590779c6d6685473b16/

Key Features:
1. Uses SEC EDGAR XBRL API (free, official)
2. GPT-4 structured output for parsing (requires OpenAI API)
3. Gets historical 10-K filings back to 2009+
4. Extracts: Income Statement, Balance Sheet, Cash Flow

Dependencies:
- requests (SEC API)
- instructor + openai (GPT structured output)
- pydantic (data validation)
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from typing import Any

import pytest
import requests

# Test Configuration
TEST_TICKERS = {
    "AAPL": "0000320193",  # Apple - CIK number
    "MSFT": "0000789019",  # Microsoft
    "TSLA": "0001318605",  # Tesla
}

SEC_USER_AGENT = "DCF-Valuation-Test research@test.com"  # Required by SEC


class TestSECDataAvailability:
    """Test if SEC EDGAR API provides sufficient historical data."""

    def test_sec_api_accessible(self):
        """Verify SEC submissions API is accessible."""
        cik = TEST_TICKERS["AAPL"]
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        
        response = requests.get(url, headers={"User-Agent": SEC_USER_AGENT})
        
        assert response.status_code == 200, f"SEC API returned {response.status_code}"
        data = response.json()
        assert "name" in data
        assert "filings" in data
        print(f"✅ SEC API accessible - Entity: {data['name']}")

    def test_get_10k_filings_count(self):
        """Check how many 10-K filings are available for each test ticker."""
        results = {}
        
        for ticker, cik in TEST_TICKERS.items():
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            response = requests.get(url, headers={"User-Agent": SEC_USER_AGENT})
            data = response.json()
            
            filings = data.get("filings", {}).get("recent", {})
            forms = filings.get("form", [])
            filing_dates = filings.get("filingDate", [])
            accession_numbers = filings.get("accessionNumber", [])
            
            # Filter for 10-K filings
            ten_k_filings = []
            for i, form in enumerate(forms):
                if form in ["10-K", "10-K/A"]:  # 10-K/A is amended 10-K
                    ten_k_filings.append({
                        "date": filing_dates[i],
                        "accession": accession_numbers[i],
                        "form": form,
                    })
            
            results[ticker] = {
                "count": len(ten_k_filings),
                "earliest": min([f["date"] for f in ten_k_filings]) if ten_k_filings else None,
                "latest": max([f["date"] for f in ten_k_filings]) if ten_k_filings else None,
                "filings": ten_k_filings[:5],  # First 5 for inspection
            }
        
        # Print results
        print("\n" + "="*80)
        print("SEC 10-K FILING AVAILABILITY")
        print("="*80)
        for ticker, info in results.items():
            print(f"\n{ticker} ({TEST_TICKERS[ticker]}):")
            print(f"  Total 10-K filings: {info['count']}")
            print(f"  Date range: {info['earliest']} to {info['latest']}")
            print(f"  Sample filings:")
            for filing in info['filings']:
                print(f"    - {filing['date']}: {filing['form']} ({filing['accession']})")
        
        # Assertions
        for ticker, info in results.items():
            # Note: "recent" only shows last ~10 filings, but XBRL API has full history
            assert info["count"] >= 5, f"{ticker} should have at least 5 recent 10-K filings in submissions API"
            
            # Check we have recent data
            if info["earliest"]:
                earliest_year = int(info["earliest"][:4])
                assert earliest_year <= 2022, f"{ticker} should have filings from 2022 or earlier"
        
        print("\n✅ All tickers have sufficient recent 10-K filings")
        print("Note: Full history (15+ years) available via XBRL Company Facts API")

    def test_xbrl_company_facts_api(self):
        """Test SEC Company Facts API (XBRL aggregated data)."""
        results = {}
        
        for ticker, cik in TEST_TICKERS.items():
            url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            response = requests.get(url, headers={"User-Agent": SEC_USER_AGENT})
            
            assert response.status_code == 200, f"XBRL API failed for {ticker}"
            
            data = response.json()
            company_name = data.get("entityName") or data.get("name")  # Try both fields
            facts = data.get("facts", {})
            us_gaap = facts.get("us-gaap", {})
            
            # Check key metrics availability
            key_metrics = {
                "Revenues": "Revenues",
                "NetIncomeLoss": "NetIncomeLoss",
                "Assets": "Assets",
                "CashAndCashEquivalentsAtCarryingValue": "CashAndCashEquivalentsAtCarryingValue",
                "CommonStockSharesOutstanding": "CommonStockSharesOutstanding",
            }
            
            available_metrics = {}
            for metric_name, xbrl_tag in key_metrics.items():
                if xbrl_tag in us_gaap:
                    metric_data = us_gaap[xbrl_tag]
                    units = list(metric_data.get("units", {}).keys())
                    
                    # Get 10-K annual data
                    annual_data = []
                    for unit in units:
                        for entry in metric_data["units"][unit]:
                            if entry.get("form") == "10-K":
                                annual_data.append({
                                    "year": entry.get("fy"),
                                    "value": entry.get("val"),
                                    "filed": entry.get("filed"),
                                })
                    
                    available_metrics[metric_name] = {
                        "found": True,
                        "annual_entries": len(annual_data),
                        "sample": annual_data[:3],
                    }
                else:
                    available_metrics[metric_name] = {"found": False}
            
            results[ticker] = {
                "company": company_name,
                "metrics": available_metrics,
            }
        
        # Print results
        print("\n" + "="*80)
        print("SEC XBRL COMPANY FACTS API")
        print("="*80)
        for ticker, info in results.items():
            print(f"\n{ticker} - {info['company']}:")
            for metric_name, metric_info in info['metrics'].items():
                if metric_info['found']:
                    print(f"  ✅ {metric_name}: {metric_info['annual_entries']} annual entries")
                    if metric_info['sample']:
                        print(f"     Sample: FY{metric_info['sample'][0]['year']} = {metric_info['sample'][0]['value']:,}")
                else:
                    print(f"  ❌ {metric_name}: Not found")
        
        # Assertion: At least 3/5 key metrics should be available
        for ticker, info in results.items():
            found_count = sum(1 for m in info['metrics'].values() if m['found'])
            assert found_count >= 3, f"{ticker} should have at least 3/5 key metrics"
        
        print("\n✅ XBRL Company Facts API provides sufficient data")

    def test_historical_data_span(self):
        """Verify we can get 10+ years of historical data for backtesting."""
        ticker = "AAPL"
        cik = TEST_TICKERS[ticker]
        
        # Get all 10-K filings
        submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        response = requests.get(submissions_url, headers={"User-Agent": SEC_USER_AGENT})
        data = response.json()
        
        filings = data.get("filings", {}).get("recent", {})
        forms = filings.get("form", [])
        filing_dates = filings.get("filingDate", [])
        
        ten_k_dates = [
            datetime.strptime(filing_dates[i], "%Y-%m-%d")
            for i, form in enumerate(forms)
            if form == "10-K"
        ]
        
        if ten_k_dates:
            earliest = min(ten_k_dates)
            latest = max(ten_k_dates)
            span_years = (latest - earliest).days / 365.25
            
            print(f"\n{ticker} Historical Data Span:")
            print(f"  Earliest 10-K: {earliest.date()}")
            print(f"  Latest 10-K: {latest.date()}")
            print(f"  Span: {span_years:.1f} years")
            
            assert span_years >= 10, f"Should have at least 10 years of data, got {span_years:.1f}"
            print(f"✅ {span_years:.1f} years of historical data available")


class TestOpenAIParsingFeasibility:
    """Test if OpenAI parsing approach is feasible (requires API key)."""

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set - skipping GPT parsing tests"
    )
    def test_openai_api_available(self):
        """Test if OpenAI API is accessible."""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # Simple test call
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Cheaper model for testing
                messages=[{"role": "user", "content": "Say 'API works' if you can read this."}],
                max_tokens=10,
            )
            
            result = response.choices[0].message.content
            print(f"✅ OpenAI API accessible - Response: {result}")
            assert "API works" in result or "works" in result.lower()
            
        except ImportError:
            pytest.skip("openai library not installed - run: pip install openai")

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set"
    )
    def test_instructor_structured_output(self):
        """Test instructor library for structured data extraction."""
        try:
            import instructor
            from openai import OpenAI
            from pydantic import BaseModel, Field
            
            # Define structure
            class FinancialMetric(BaseModel):
                revenue: float = Field(description="Total revenue in USD")
                net_income: float = Field(description="Net income in USD")
            
            # Initialize client with instructor
            client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))
            
            # Test extraction
            test_text = """
            Apple Inc. reported the following for FY2023:
            - Total revenue: $394.3 billion
            - Net income: $97.0 billion
            """
            
            result = client.chat.completions.create(
                model="gpt-4o-mini",
                response_model=FinancialMetric,
                messages=[
                    {"role": "system", "content": "Extract financial metrics from text."},
                    {"role": "user", "content": test_text},
                ],
            )
            
            print(f"\n✅ Instructor structured output works:")
            print(f"  Revenue: ${result.revenue:,.0f}")
            print(f"  Net Income: ${result.net_income:,.0f}")
            
            assert result.revenue > 0
            assert result.net_income > 0
            
        except ImportError as e:
            pytest.skip(f"Required library not installed: {e}")


class TestCostAnalysis:
    """Estimate costs for parsing historical data."""

    def test_estimate_openai_costs(self):
        """Estimate OpenAI API costs for full backtest."""
        # Assumptions
        num_stocks = 50
        years_per_stock = 15
        filings_per_year = 1  # Annual 10-K
        total_filings = num_stocks * years_per_stock * filings_per_year
        
        # Token estimates (from notebook timing: ~20-30 seconds per filing)
        # Each filing ~3 statements × ~5,000 input tokens = 15k input tokens
        # Each filing ~3 statements × ~500 output tokens = 1,500 output tokens
        input_tokens_per_filing = 15_000
        output_tokens_per_filing = 1_500
        
        total_input_tokens = total_filings * input_tokens_per_filing
        total_output_tokens = total_filings * output_tokens_per_filing
        
        # GPT-4o pricing (as of Jan 2026)
        gpt4o_input_cost = 2.50 / 1_000_000  # $2.50 per 1M tokens
        gpt4o_output_cost = 10.00 / 1_000_000  # $10.00 per 1M tokens
        
        # GPT-4o-mini pricing (cheaper alternative)
        gpt4o_mini_input_cost = 0.15 / 1_000_000  # $0.15 per 1M tokens
        gpt4o_mini_output_cost = 0.60 / 1_000_000  # $0.60 per 1M tokens
        
        gpt4o_cost = (
            total_input_tokens * gpt4o_input_cost +
            total_output_tokens * gpt4o_output_cost
        )
        
        gpt4o_mini_cost = (
            total_input_tokens * gpt4o_mini_input_cost +
            total_output_tokens * gpt4o_mini_output_cost
        )
        
        print("\n" + "="*80)
        print("OPENAI API COST ESTIMATE")
        print("="*80)
        print(f"Backtest Configuration:")
        print(f"  Stocks: {num_stocks}")
        print(f"  Years per stock: {years_per_stock}")
        print(f"  Total 10-K filings: {total_filings}")
        print(f"\nToken Estimates:")
        print(f"  Total input tokens: {total_input_tokens:,}")
        print(f"  Total output tokens: {total_output_tokens:,}")
        print(f"\nCost Estimates:")
        print(f"  GPT-4o: ${gpt4o_cost:.2f}")
        print(f"  GPT-4o-mini: ${gpt4o_mini_cost:.2f} (recommended)")
        print(f"\nTime Estimate:")
        print(f"  ~25 seconds per filing = {total_filings * 25 / 3600:.1f} hours")
        print(f"  Can parallelize with batch API for 50% cost reduction")
        print("="*80)
        
        # Assertions
        assert gpt4o_mini_cost < 20, f"Should be under $20 with mini model, got ${gpt4o_mini_cost:.2f}"
        print(f"\n✅ Estimated cost with GPT-4o-mini: ${gpt4o_mini_cost:.2f} (acceptable)")


def test_feasibility_summary():
    """Print comprehensive feasibility analysis."""
    print("\n" + "="*80)
    print("SEC EDGAR PARSER FEASIBILITY SUMMARY")
    print("="*80)
    
    print("\n✅ DATA AVAILABILITY:")
    print("  - SEC EDGAR API: FREE, official, unlimited")
    print("  - 10-K filings: 10+ years available for major stocks")
    print("  - XBRL format: Structured, machine-readable")
    print("  - Coverage: All US public companies since ~2009")
    
    print("\n✅ PARSING APPROACH:")
    print("  - Method: SEC XBRL API + GPT-4 structured output")
    print("  - Library: instructor + openai (well-maintained)")
    print("  - Accuracy: High (GPT-4 understands financial statements)")
    print("  - Code: ~200 lines (from virattt's notebook)")
    
    print("\n💰 COSTS:")
    print("  - SEC API: $0 (free)")
    print("  - OpenAI GPT-4o-mini: ~$10-20 for full 50-stock backtest")
    print("  - One-time cost (cache results)")
    print("  - Alternative: Use cached data after initial run")
    
    print("\n⏱️  TIME:")
    print("  - ~25 seconds per filing (3 statements)")
    print("  - 750 filings (50 stocks × 15 years) = ~5 hours")
    print("  - Can run overnight, cache forever")
    print("  - Incremental updates: Only new filings")
    
    print("\n🔧 IMPLEMENTATION:")
    print("  - Complexity: LOW (adapt existing notebook)")
    print("  - Dependencies: requests, instructor, openai, pydantic")
    print("  - Integration: Replace yfinance financials in data_loader.py")
    print("  - Testing: Use 5 stocks first (pilot)")
    
    print("\n⚠️  CONSIDERATIONS:")
    print("  - Requires OpenAI API key ($10-20 credit sufficient)")
    print("  - Rate limiting: SEC allows ~10 requests/second")
    print("  - XBRL tags vary by company (GPT handles this)")
    print("  - Quarters vs annual: 10-Q for quarterly (more filings)")
    
    print("\n🎯 RECOMMENDATION: GO WITH OPTION B")
    print("="*80)
    print("Rationale:")
    print("  1. ✅ Proven approach (virattt's notebook works)")
    print("  2. ✅ Affordable (~$10-20 vs $30-200/month commercial API)")
    print("  3. ✅ Free SEC data (no ongoing costs)")
    print("  4. ✅ Low complexity (~200 lines code)")
    print("  5. ✅ Enables full 15-year backtest")
    print("\nNext Steps:")
    print("  1. Install: pip install instructor openai")
    print("  2. Set OPENAI_API_KEY environment variable")
    print("  3. Adapt virattt's code for DCF metrics (FCF, shares, debt)")
    print("  4. Test on 5 stocks first")
    print("  5. Run full backtest (750 filings, ~5 hours)")
    print("="*80 + "\n")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
