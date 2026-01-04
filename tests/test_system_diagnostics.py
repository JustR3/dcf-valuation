"""System Diagnostics - Critical Analysis of Current DCF System.

This test runs the current system on 20 diverse stocks and captures:
1. Terminal value proportion (looking for >75% dominance)
2. DCF vs Relative valuation conflicts
3. Monte Carlo confidence intervals (looking for 95-99% false precision)
4. Implied margin expansion requirements
5. Growth rate reality checks

The goal is to diagnose WHERE the system breaks, not to validate it works.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from src.dcf_engine import DCFEngine
from src.logging_config import get_logger

logger = get_logger(__name__)


# Diverse stock selection covering different scenarios
DIAGNOSTIC_STOCKS = {
    # Mature, stable companies
    "KO": "Mature Consumer - Coca-Cola",
    "PG": "Mature Consumer - Procter & Gamble", 
    "JNJ": "Mature Healthcare - Johnson & Johnson",
    
    # High-growth tech
    "NVDA": "High-growth Tech - NVIDIA",
    "NOW": "High-growth SaaS - ServiceNow",
    "PLTR": "High-growth AI - Palantir",
    
    # Mega-cap tech (mature but still growing)
    "AAPL": "Mega-cap Tech - Apple",
    "MSFT": "Mega-cap Tech - Microsoft",
    "GOOGL": "Mega-cap Tech - Google",
    
    # Cyclicals
    "F": "Cyclical Auto - Ford",
    "GM": "Cyclical Auto - GM",
    "CF": "Cyclical Materials - CF Industries",
    
    # Turnarounds
    "INTC": "Turnaround - Intel",
    "IBM": "Turnaround - IBM",
    
    # Loss-making growth
    "RIVN": "Loss-making EV - Rivian",
    "RDDT": "Loss-making Tech - Reddit",
    
    # Financials
    "JPM": "Financial - JPMorgan",
    "BAC": "Financial - Bank of America",
    
    # Value/defensive
    "T": "Defensive Telecom - AT&T",
    "VZ": "Defensive Telecom - Verizon",
}


@dataclass
class DiagnosticResult:
    """Container for diagnostic analysis of a single stock."""
    ticker: str
    description: str
    
    # Basic valuation
    current_price: float
    dcf_fair_value: float
    dcf_upside: float
    
    # Terminal value analysis
    terminal_value_pct: float  # % of enterprise value
    terminal_method: str
    
    # Growth assumptions
    analyst_growth: float | None
    growth_used: float
    revenue_5y_cagr: float | None
    
    # Relative valuation comparison
    relative_signal: str  # UNDERVALUED / FAIR / OVERVALUED
    relative_upside: float | None
    dcf_vs_relative_conflict: bool
    
    # Monte Carlo analysis
    mc_probability: float  # % probability undervalued
    mc_confidence_interval: tuple[float, float]  # (5th, 95th percentile)
    mc_interval_width: float  # How wide is the confidence band
    
    # Red flags
    warnings: list[str]
    
    # Raw result for deep dive
    raw_result: dict
    
    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "description": self.description,
            "current_price": float(self.current_price),
            "dcf_fair_value": float(self.dcf_fair_value),
            "dcf_upside": float(self.dcf_upside),
            "terminal_value_pct": float(self.terminal_value_pct),
            "terminal_method": self.terminal_method,
            "analyst_growth": float(self.analyst_growth) if self.analyst_growth else None,
            "growth_used": float(self.growth_used),
            "revenue_5y_cagr": float(self.revenue_5y_cagr) if self.revenue_5y_cagr else None,
            "relative_signal": self.relative_signal,
            "relative_upside": float(self.relative_upside) if self.relative_upside else None,
            "dcf_vs_relative_conflict": bool(self.dcf_vs_relative_conflict),
            "mc_probability": float(self.mc_probability),
            "mc_confidence_interval": (float(self.mc_confidence_interval[0]), float(self.mc_confidence_interval[1])),
            "mc_interval_width": float(self.mc_interval_width),
            "warnings": self.warnings,
        }


def analyze_stock(ticker: str, description: str) -> DiagnosticResult | None:
    """Run full DCF analysis and extract diagnostic metrics."""
    try:
        logger.info(f"Analyzing {ticker}: {description}")
        
        # Initialize engine and fetch data
        engine = DCFEngine(ticker, auto_fetch=True)
        
        if not engine.is_ready:
            logger.warning(f"❌ {ticker}: Failed to fetch data - {engine.last_error}")
            return None
        
        data = engine.company_data
        
        # Get DCF valuation
        dcf_result = engine.get_intrinsic_value()
        
        # Skip if valuation failed
        if dcf_result.get('error'):
            logger.warning(f"❌ {ticker}: DCF calculation failed - {dcf_result['error']}")
            return None
        
        # Get Monte Carlo simulation
        from src.cli.display import enrich_dcf_with_monte_carlo
        enriched = enrich_dcf_with_monte_carlo(engine, dcf_result)
        
        # Extract metrics
        warnings = []
        
        # 1. Terminal value dominance
        # Note: EV/Sales valuations don't have terminal value breakdown
        terminal_value_pct = 0
        if 'term_pv' in enriched and enriched.get('enterprise_value', 0) > 0:
            terminal_value_pct = (
                enriched['term_pv'] / enriched['enterprise_value'] * 100
            )
        
        if terminal_value_pct > 75:
            warnings.append(f"Terminal value dominates: {terminal_value_pct:.1f}% of EV")
        
        # 2. DCF vs Relative conflict
        relative_val = enriched.get('relative_valuation', {})
        relative_signal = relative_val.get('overall_assessment', 'UNKNOWN')
        
        dcf_upside = enriched['upside_downside']
        dcf_bullish = dcf_upside > 20
        dcf_bearish = dcf_upside < -10
        
        rel_bullish = relative_signal == 'UNDERVALUED'
        rel_bearish = relative_signal == 'OVERVALUED'
        
        conflict = (dcf_bullish and rel_bearish) or (dcf_bearish and rel_bullish)
        
        if conflict:
            warnings.append(
                f"DCF vs Relative CONFLICT: DCF {dcf_upside:+.1f}% vs Relative {relative_signal}"
            )
        
        # 3. Blended fair value vs DCF fair value
        blended_val = enriched.get('blended_valuation', {})
        relative_upside = None
        
        if blended_val:
            blended_value = blended_val.get('blended_value')
            if blended_value:
                relative_upside = (
                    (blended_value - data.current_price) / data.current_price * 100
                    if data.current_price > 0 else 0
                )
                
                # Check if blending significantly changed the upside
                if abs(dcf_upside - relative_upside) > 30:
                    warnings.append(
                        f"Large blending adjustment: DCF {dcf_upside:+.1f}% → "
                        f"Blended {relative_upside:+.1f}%"
                    )
        
        # 4. Monte Carlo overconfidence
        mc_data = enriched.get('monte_carlo', {})
        mc_probability = mc_data.get('probability', 0) if mc_data else 0
        var_95 = mc_data.get('var_95', 0) if mc_data else 0
        upside_95 = mc_data.get('upside_95', 0) if mc_data else 0
        
        mc_interval_width = (
            (upside_95 - var_95) / data.current_price * 100
            if data.current_price > 0 else 0
        )
        
        if mc_probability > 95:
            warnings.append(f"Monte Carlo overconfident: {mc_probability:.1f}% probability")
        
        if mc_interval_width < 20:
            warnings.append(
                f"Monte Carlo too narrow: {mc_interval_width:.1f}% confidence interval"
            )
        
        # 5. Growth rate reality check
        analyst_growth = data.analyst_growth
        growth_used = enriched['inputs']['growth']
        
        # Try to get revenue CAGR (will be None in current system)
        revenue_cagr = data.revenue  # Placeholder - not currently calculated
        
        if analyst_growth and analyst_growth > 0.30:
            warnings.append(f"Very high analyst growth: {analyst_growth*100:.1f}%")
        
        # 6. PEG ratio check
        peg = data.peg_ratio
        if peg and peg > 2.0:
            warnings.append(f"High PEG ratio: {peg:.2f} (growth priced in)")
        
        # 7. Extreme valuations
        if abs(dcf_upside) > 100:
            warnings.append(f"Extreme valuation: {dcf_upside:+.1f}% upside")
        
        return DiagnosticResult(
            ticker=ticker,
            description=description,
            current_price=data.current_price,
            dcf_fair_value=enriched['value_per_share'],
            dcf_upside=dcf_upside,
            terminal_value_pct=terminal_value_pct,
            terminal_method=enriched['inputs']['terminal_method'],
            analyst_growth=analyst_growth,
            growth_used=growth_used,
            revenue_5y_cagr=None,  # Not calculated yet
            relative_signal=relative_signal,
            relative_upside=relative_upside,
            dcf_vs_relative_conflict=conflict,
            mc_probability=mc_probability,
            mc_confidence_interval=(var_95, upside_95),
            mc_interval_width=mc_interval_width,
            warnings=warnings,
            raw_result=enriched,
        )
        
    except Exception as e:
        logger.error(f"❌ {ticker}: Unexpected error - {str(e)}")
        return None


def run_diagnostics() -> dict:
    """Run diagnostic analysis on all stocks."""
    print("=" * 80)
    print("DCF SYSTEM DIAGNOSTICS - CRITICAL ANALYSIS")
    print("=" * 80)
    print(f"\nRunning diagnostics on {len(DIAGNOSTIC_STOCKS)} stocks...")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    results = []
    failed = []
    
    for ticker, description in DIAGNOSTIC_STOCKS.items():
        try:
            result = analyze_stock(ticker, description)
            if result:
                results.append(result)
                print(f"✅ {ticker}: {len(result.warnings)} warnings")
            else:
                failed.append(ticker)
                print(f"❌ {ticker}: Failed")
            
            # Rate limiting
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"❌ {ticker}: Critical error - {str(e)}")
            failed.append(ticker)
    
    print(f"\n{'=' * 80}")
    print(f"Diagnostics complete: {len(results)} succeeded, {len(failed)} failed")
    print(f"{'=' * 80}\n")
    
    return {
        "results": results,
        "failed": failed,
        "timestamp": datetime.now().isoformat(),
    }


def analyze_patterns(diagnostic_data: dict) -> dict:
    """Analyze patterns across all stocks to identify systemic issues."""
    results = diagnostic_data['results']
    
    if not results:
        return {"error": "No results to analyze"}
    
    analysis = {
        "summary": {
            "total_stocks": len(results),
            "failed_stocks": len(diagnostic_data['failed']),
        },
        "terminal_value_analysis": {},
        "conflict_analysis": {},
        "monte_carlo_analysis": {},
        "growth_analysis": {},
        "valuation_extremes": {},
        "worst_offenders": [],
    }
    
    # 1. Terminal value dominance
    terminal_pcts = [r.terminal_value_pct for r in results]
    analysis["terminal_value_analysis"] = {
        "average_terminal_pct": np.mean(terminal_pcts),
        "median_terminal_pct": np.median(terminal_pcts),
        "max_terminal_pct": np.max(terminal_pcts),
        "stocks_above_75pct": sum(1 for pct in terminal_pcts if pct > 75),
        "stocks_above_80pct": sum(1 for pct in terminal_pcts if pct > 80),
    }
    
    # 2. DCF vs Relative conflicts
    conflicts = [r for r in results if r.dcf_vs_relative_conflict]
    analysis["conflict_analysis"] = {
        "total_conflicts": len(conflicts),
        "conflict_rate": len(conflicts) / len(results) * 100,
        "conflicted_stocks": [
            {
                "ticker": r.ticker,
                "dcf_upside": r.dcf_upside,
                "relative_signal": r.relative_signal,
            }
            for r in conflicts
        ],
    }
    
    # 3. Monte Carlo overconfidence
    mc_probs = [r.mc_probability for r in results]
    mc_widths = [r.mc_interval_width for r in results]
    
    analysis["monte_carlo_analysis"] = {
        "average_probability": np.mean(mc_probs),
        "median_probability": np.median(mc_probs),
        "stocks_above_95pct": sum(1 for p in mc_probs if p > 95),
        "stocks_above_90pct": sum(1 for p in mc_probs if p > 90),
        "average_interval_width": np.mean(mc_widths),
        "stocks_too_narrow": sum(1 for w in mc_widths if w < 20),
    }
    
    # 4. Growth rate analysis
    high_growth_stocks = [r for r in results if r.analyst_growth and r.analyst_growth > 0.20]
    analysis["growth_analysis"] = {
        "high_growth_count": len(high_growth_stocks),
        "high_growth_stocks": [
            {
                "ticker": r.ticker,
                "analyst_growth": r.analyst_growth * 100,
                "growth_used": r.growth_used * 100,
            }
            for r in high_growth_stocks
        ],
    }
    
    # 5. Extreme valuations
    extreme_upsides = [r for r in results if abs(r.dcf_upside) > 100]
    analysis["valuation_extremes"] = {
        "extreme_count": len(extreme_upsides),
        "extreme_stocks": [
            {
                "ticker": r.ticker,
                "upside": r.dcf_upside,
                "fair_value": r.dcf_fair_value,
                "current_price": r.current_price,
            }
            for r in extreme_upsides
        ],
    }
    
    # 6. Identify worst offenders (most warnings)
    sorted_by_warnings = sorted(results, key=lambda r: len(r.warnings), reverse=True)
    analysis["worst_offenders"] = [
        {
            "ticker": r.ticker,
            "description": r.description,
            "warning_count": len(r.warnings),
            "warnings": r.warnings,
            "dcf_upside": r.dcf_upside,
            "terminal_value_pct": r.terminal_value_pct,
            "mc_probability": r.mc_probability,
        }
        for r in sorted_by_warnings[:10]  # Top 10 worst
    ]
    
    return analysis


def generate_critical_report(diagnostic_data: dict, pattern_analysis: dict) -> str:
    """Generate critical analysis report highlighting systemic failures."""
    report_lines = []
    
    report_lines.append("=" * 80)
    report_lines.append("DCF SYSTEM DIAGNOSTIC REPORT - CRITICAL FINDINGS")
    report_lines.append("=" * 80)
    report_lines.append("")
    
    # Summary
    summary = pattern_analysis['summary']
    report_lines.append(f"Total Stocks Analyzed: {summary['total_stocks']}")
    report_lines.append(f"Failed to Analyze: {summary['failed_stocks']}")
    report_lines.append("")
    
    # Finding 1: Terminal Value Dominance
    report_lines.append("FINDING 1: TERMINAL VALUE DOMINANCE")
    report_lines.append("-" * 80)
    tv_analysis = pattern_analysis['terminal_value_analysis']
    report_lines.append(f"Average Terminal Value: {tv_analysis['average_terminal_pct']:.1f}% of EV")
    report_lines.append(f"Stocks with Terminal > 75%: {tv_analysis['stocks_above_75pct']}")
    report_lines.append(f"Stocks with Terminal > 80%: {tv_analysis['stocks_above_80pct']}")
    
    if tv_analysis['stocks_above_75pct'] > summary['total_stocks'] * 0.5:
        report_lines.append("")
        report_lines.append("⚠️  CRITICAL: More than 50% of valuations dominated by terminal value!")
        report_lines.append("    This means fair value is highly sensitive to perpetual growth assumptions.")
        report_lines.append("    Small changes in terminal growth rate cause massive valuation swings.")
    report_lines.append("")
    
    # Finding 2: DCF vs Relative Conflicts
    report_lines.append("FINDING 2: DCF VS RELATIVE VALUATION CONFLICTS")
    report_lines.append("-" * 80)
    conflict_analysis = pattern_analysis['conflict_analysis']
    report_lines.append(f"Conflict Rate: {conflict_analysis['conflict_rate']:.1f}%")
    report_lines.append(f"Total Conflicts: {conflict_analysis['total_conflicts']}")
    
    if conflict_analysis['conflicted_stocks']:
        report_lines.append("\nConflicting Stocks:")
        for stock in conflict_analysis['conflicted_stocks'][:5]:  # Top 5
            report_lines.append(
                f"  - {stock['ticker']}: DCF {stock['dcf_upside']:+.1f}% vs "
                f"Relative {stock['relative_signal']}"
            )
    
    if conflict_analysis['conflict_rate'] > 25:
        report_lines.append("")
        report_lines.append("⚠️  CRITICAL: High conflict rate between DCF and market-based valuation!")
        report_lines.append("    System provides contradictory signals with no warnings to user.")
    report_lines.append("")
    
    # Finding 3: Monte Carlo Overconfidence
    report_lines.append("FINDING 3: MONTE CARLO OVERCONFIDENCE")
    report_lines.append("-" * 80)
    mc_analysis = pattern_analysis['monte_carlo_analysis']
    report_lines.append(f"Average Probability: {mc_analysis['average_probability']:.1f}%")
    report_lines.append(f"Stocks with >95% Confidence: {mc_analysis['stocks_above_95pct']}")
    report_lines.append(f"Stocks with >90% Confidence: {mc_analysis['stocks_above_90pct']}")
    report_lines.append(f"Average Confidence Interval Width: {mc_analysis['average_interval_width']:.1f}%")
    report_lines.append(f"Stocks with <20% Interval: {mc_analysis['stocks_too_narrow']}")
    
    if mc_analysis['stocks_above_95pct'] > 3:
        report_lines.append("")
        report_lines.append("⚠️  CRITICAL: Multiple stocks showing >95% confidence - unrealistic!")
        report_lines.append("    DCF inputs have 15-20% inherent uncertainty.")
        report_lines.append("    Monte Carlo is sampling around bad assumptions (GIGO).")
    report_lines.append("")
    
    # Finding 4: Extreme Valuations
    report_lines.append("FINDING 4: EXTREME VALUATIONS")
    report_lines.append("-" * 80)
    extreme_analysis = pattern_analysis['valuation_extremes']
    report_lines.append(f"Stocks with >100% Absolute Upside: {extreme_analysis['extreme_count']}")
    
    if extreme_analysis['extreme_stocks']:
        report_lines.append("\nExtreme Valuations:")
        for stock in extreme_analysis['extreme_stocks'][:5]:
            report_lines.append(
                f"  - {stock['ticker']}: {stock['upside']:+.1f}% "
                f"(${stock['current_price']:.2f} → ${stock['fair_value']:.2f})"
            )
    
    if extreme_analysis['extreme_count'] > 0:
        report_lines.append("")
        report_lines.append("⚠️  WARNING: Extreme valuations suggest unrealistic assumptions.")
        report_lines.append("    Market is unlikely to be THIS wrong about well-followed stocks.")
    report_lines.append("")
    
    # Top 10 Worst Offenders
    report_lines.append("TOP 10 WORST OFFENDERS (Most Warnings)")
    report_lines.append("-" * 80)
    
    for i, stock in enumerate(pattern_analysis['worst_offenders'], 1):
        report_lines.append(f"\n{i}. {stock['ticker']} - {stock['description']}")
        report_lines.append(f"   Warnings: {stock['warning_count']}")
        report_lines.append(f"   DCF Upside: {stock['dcf_upside']:+.1f}%")
        report_lines.append(f"   Terminal Value: {stock['terminal_value_pct']:.1f}%")
        report_lines.append(f"   MC Probability: {stock['mc_probability']:.1f}%")
        for warning in stock['warnings']:
            report_lines.append(f"   ⚠️  {warning}")
    
    report_lines.append("")
    report_lines.append("=" * 80)
    report_lines.append("END OF DIAGNOSTIC REPORT")
    report_lines.append("=" * 80)
    
    return "\n".join(report_lines)


def save_results(diagnostic_data: dict, pattern_analysis: dict, report: str) -> None:
    """Save diagnostic results to files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save raw results as JSON
    results_file = f"data/diagnostics_results_{timestamp}.json"
    with open(results_file, 'w') as f:
        # Convert DiagnosticResult objects to dicts
        serializable_data = {
            "results": [r.to_dict() for r in diagnostic_data['results']],
            "failed": diagnostic_data['failed'],
            "timestamp": diagnostic_data['timestamp'],
        }
        json.dump(serializable_data, f, indent=2)
    
    # Save pattern analysis
    analysis_file = f"data/diagnostics_analysis_{timestamp}.json"
    with open(analysis_file, 'w') as f:
        json.dump(pattern_analysis, f, indent=2)
    
    # Save report as text
    report_file = f"data/diagnostics_report_{timestamp}.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\n✅ Results saved:")
    print(f"   - {results_file}")
    print(f"   - {analysis_file}")
    print(f"   - {report_file}")


def test_run_system_diagnostics():
    """Main test function to run diagnostics."""
    # Run diagnostics
    diagnostic_data = run_diagnostics()
    
    # Analyze patterns
    pattern_analysis = analyze_patterns(diagnostic_data)
    
    # Generate report
    report = generate_critical_report(diagnostic_data, pattern_analysis)
    
    # Print report
    print("\n" + report)
    
    # Save results
    save_results(diagnostic_data, pattern_analysis, report)
    
    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Review the report above to identify systemic issues")
    print("2. Check saved files in data/ for detailed analysis")
    print("3. Prioritize fixes based on frequency and severity of issues")
    print("4. Consider root cause: bad assumptions vs bad methodology")
    print("=" * 80)


if __name__ == "__main__":
    test_run_system_diagnostics()
