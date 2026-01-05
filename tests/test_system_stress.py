"""
Comprehensive System Stress Test
=================================

Tests 50+ stocks across all 11 sectors to validate:
1. DCF calculation robustness
2. Error handling under various data conditions
3. Dependency on external analyst estimates vs internal calculations
4. Data quality validation
5. Edge case handling (negative growth, missing data, etc.)

This test is designed to expose:
- Logic flaws in DCF calculations
- Over-reliance on external data
- Calculation inconsistencies across sectors
- Data validation gaps
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import pytest

from src.config import SECTOR_PEERS
from src.dcf_engine import DCFEngine
from src.exceptions import ValidationError


# Select 3-4 stocks per sector for comprehensive coverage
# Prioritize: diverse market caps, different growth profiles, data quality variation
STRESS_TEST_STOCKS = {
    "Technology": ["AAPL", "NVDA", "INTC", "IBM"],  # Mix of growth & value
    "Communication Services": ["META", "NFLX", "T", "VZ"],  # High/low growth mix
    "Healthcare": ["LLY", "JNJ", "PFE", "ABBV"],  # Pharma diversity
    "Consumer Cyclical": ["AMZN", "TSLA", "MCD", "F"],  # Growth vs mature
    "Consumer Defensive": ["WMT", "PG", "KO", "PM"],  # Stable defensives
    "Industrials": ["CAT", "BA", "UPS", "GE"],  # Cyclical industrials
    "Financial Services": ["JPM", "BAC", "BRK.B", "V"],  # Banks & payments
    "Energy": ["XOM", "CVX", "COP", "SLB"],  # Integrated & service
    "Utilities": ["NEE", "SO", "DUK", "AEP"],  # Regulated utilities
    "Real Estate": ["PLD", "AMT", "PSA", "O"],  # REITs diversity
    "Basic Materials": ["LIN", "APD", "NEM", "FCX"],  # Chemicals & mining
}


@dataclass
class StressTestResult:
    """Individual stock stress test result."""

    ticker: str
    sector: str
    success: bool
    error_type: str | None
    error_message: str | None

    # DCF Validation Metrics
    intrinsic_value: float | None
    current_price: float | None
    upside_pct: float | None

    # Data Quality Flags
    has_analyst_growth: bool
    has_historical_fcf: bool
    has_valid_wacc: bool
    calculated_growth_rate: float | None
    analyst_growth_rate: float | None
    growth_rate_used: float | None

    # Calculation Validation
    wacc: float | None
    terminal_growth: float | None
    fcf_year_1: float | None
    fcf_year_5: float | None
    present_value_fcf: float | None
    terminal_value: float | None

    # Risk Metrics
    monte_carlo_stdev: float | None
    probability_upside: float | None

    # Data Dependency Analysis
    relies_on_external_growth: bool
    calculation_method: str | None  # "internal_only", "analyst_only", "hybrid"

    # Warnings & Issues
    warnings: list[str]


class DCFStressTester:
    """Comprehensive DCF system stress tester."""

    def __init__(self):
        self.results: list[StressTestResult] = []

    def test_stock(self, ticker: str, sector: str) -> StressTestResult:
        """
        Test individual stock and collect comprehensive diagnostics.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        sector : str
            Sector classification

        Returns
        -------
        StressTestResult
            Detailed test results and diagnostics
        """
        warnings = []

        try:
            # Create engine instance for this ticker
            engine = DCFEngine(ticker, auto_fetch=True)
            
            # Check if data loaded successfully
            if not engine.is_ready:
                raise ValidationError(f"Failed to load data: {engine.last_error}")
            
            # Run full DCF valuation
            valuation = engine.get_intrinsic_value()

            # Extract key metrics (matching actual return structure)
            intrinsic_value = valuation.get("value_per_share")
            current_price = valuation.get("current_price")
            upside_pct = valuation.get("upside_downside")

            # Extract DCF inputs
            inputs = valuation.get("inputs", {})
            wacc = inputs.get("wacc")
            terminal_growth = inputs.get("term_growth")
            growth_used = inputs.get("growth")

            # Extract cash flow projections
            fcf_projections = valuation.get("cash_flows", [])
            
            # Check for FCF (cash_flows returns list of dicts with 'fcf' key)
            fcf_values = [cf.get('fcf', 0) if isinstance(cf, dict) else cf for cf in fcf_projections]

            # Extract company data for growth rate analysis
            company_data = valuation.get("company_data", {})
            analyst_growth = company_data.get("analyst_growth")
            
            # Check if historical FCF data exists (via company_data)
            fcf = company_data.get("fcf")
            has_historical = fcf is not None and fcf != 0
            
            # For calculated growth, we need to check if there's historical data
            # The engine calculates growth internally, so we mark as "calculated" if not from analyst
            calculated_growth = None
            if growth_used and analyst_growth:
                # If they differ significantly, some calculation was involved
                if abs(growth_used - analyst_growth) > 0.01:
                    calculated_growth = growth_used

            # Extract valuation components
            present_value_fcf = valuation.get("pv_explicit")
            terminal_value = valuation.get("term_pv")

            # Check for Monte Carlo (not in basic get_intrinsic_value, would need separate call)
            mc_stdev = None
            probability_upside = None

            # Data quality checks
            has_analyst = analyst_growth is not None
            has_wacc = wacc is not None and wacc > 0

            # Determine calculation method
            if growth_used is not None:
                if has_analyst and not has_historical:
                    calc_method = "analyst_only"
                    warnings.append("Relies solely on analyst estimates for growth")
                elif has_historical and not has_analyst:
                    calc_method = "internal_only"
                elif has_analyst and has_historical:
                    calc_method = "hybrid"
                    # Check if heavily weighted toward analyst
                    if abs(growth_used - analyst_growth) < 0.01:
                        warnings.append("Growth rate heavily weighted to analyst estimate")
                else:
                    calc_method = "default_fallback"
                    warnings.append("Using default/fallback growth rate")
            else:
                calc_method = "unknown"
                warnings.append("Unable to determine growth rate calculation method")

            # Validation checks
            if intrinsic_value is None or intrinsic_value <= 0:
                warnings.append("Invalid intrinsic value calculated")

            if wacc is None or wacc <= 0:
                warnings.append("Invalid WACC")

            if terminal_growth is not None and wacc and terminal_growth >= wacc:
                warnings.append(f"Terminal growth ({terminal_growth:.2%}) >= WACC ({wacc:.2%})")

            if growth_used is not None and abs(growth_used) > 0.5:
                warnings.append(f"Extreme growth rate: {growth_used:.2%}")

            if len(fcf_values) < 5:
                warnings.append(f"Insufficient FCF projections: {len(fcf_values)} years")

            # Check for negative FCFs
            if fcf_values and any(fcf <= 0 for fcf in fcf_values):
                warnings.append("Negative projected free cash flows detected")

            # FCF bounds
            fcf_year_1 = fcf_values[0] if fcf_values else None
            fcf_year_5 = fcf_values[-1] if fcf_values else None

            return StressTestResult(
                ticker=ticker,
                sector=sector,
                success=True,
                error_type=None,
                error_message=None,
                intrinsic_value=intrinsic_value,
                current_price=current_price,
                upside_pct=upside_pct,
                has_analyst_growth=has_analyst,
                has_historical_fcf=has_historical,
                has_valid_wacc=has_wacc,
                calculated_growth_rate=calculated_growth,
                analyst_growth_rate=analyst_growth,
                growth_rate_used=growth_used,
                wacc=wacc,
                terminal_growth=terminal_growth,
                fcf_year_1=fcf_year_1,
                fcf_year_5=fcf_year_5,
                present_value_fcf=present_value_fcf,
                terminal_value=terminal_value,
                monte_carlo_stdev=mc_stdev,
                probability_upside=probability_upside,
                relies_on_external_growth=(calc_method == "analyst_only"),
                calculation_method=calc_method,
                warnings=warnings,
            )

        except ValidationError as e:
            # Expected validation errors (e.g., missing data)
            return StressTestResult(
                ticker=ticker,
                sector=sector,
                success=False,
                error_type="ValidationError",
                error_message=str(e),
                intrinsic_value=None,
                current_price=None,
                upside_pct=None,
                has_analyst_growth=False,
                has_historical_fcf=False,
                has_valid_wacc=False,
                calculated_growth_rate=None,
                analyst_growth_rate=None,
                growth_rate_used=None,
                wacc=None,
                terminal_growth=None,
                fcf_year_1=None,
                fcf_year_5=None,
                present_value_fcf=None,
                terminal_value=None,
                monte_carlo_stdev=None,
                probability_upside=None,
                relies_on_external_growth=False,
                calculation_method=None,
                warnings=[str(e)],
            )

        except Exception as e:
            # Unexpected errors - these indicate bugs
            import traceback
            error_details = traceback.format_exc()
            
            return StressTestResult(
                ticker=ticker,
                sector=sector,
                success=False,
                error_type=type(e).__name__,
                error_message=f"{str(e)}\n\nTraceback:\n{error_details}",
                intrinsic_value=None,
                current_price=None,
                upside_pct=None,
                has_analyst_growth=False,
                has_historical_fcf=False,
                has_valid_wacc=False,
                calculated_growth_rate=None,
                analyst_growth_rate=None,
                growth_rate_used=None,
                wacc=None,
                terminal_growth=None,
                fcf_year_1=None,
                fcf_year_5=None,
                present_value_fcf=None,
                terminal_value=None,
                monte_carlo_stdev=None,
                probability_upside=None,
                relies_on_external_growth=False,
                calculation_method=None,
                warnings=[f"UNEXPECTED ERROR: {type(e).__name__}: {str(e)}"],
            )

    def run_all_tests(self) -> list[StressTestResult]:
        """Run stress test on all selected stocks."""
        print(f"\n{'='*80}")
        print("DCF SYSTEM STRESS TEST")
        print(f"{'='*80}")
        print(f"Testing {sum(len(stocks) for stocks in STRESS_TEST_STOCKS.values())} stocks across {len(STRESS_TEST_STOCKS)} sectors")
        print(f"{'='*80}\n")

        for sector, tickers in STRESS_TEST_STOCKS.items():
            print(f"\nTesting {sector} ({len(tickers)} stocks)...")
            for ticker in tickers:
                print(f"  Testing {ticker}...", end=" ")
                result = self.test_stock(ticker, sector)
                self.results.append(result)

                if result.success:
                    print(f"✓ Success (${result.intrinsic_value:,.0f}, {result.upside_pct:+.1f}%)")
                else:
                    print(f"✗ Failed ({result.error_type})")

        return self.results

    def generate_report(self) -> dict[str, Any]:
        """
        Generate comprehensive stress test report.

        Returns
        -------
        dict
            Detailed statistics and findings
        """
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total - successful

        # Error analysis
        error_types = {}
        for r in self.results:
            if not r.success and r.error_type:
                error_types[r.error_type] = error_types.get(r.error_type, 0) + 1

        # Data dependency analysis
        relies_on_external = sum(1 for r in self.results if r.relies_on_external_growth)
        calculation_methods = {}
        for r in self.results:
            if r.calculation_method:
                method = r.calculation_method
                calculation_methods[method] = calculation_methods.get(method, 0) + 1

        # Warning analysis
        all_warnings = []
        for r in self.results:
            all_warnings.extend(r.warnings)

        warning_counts = {}
        for warning in all_warnings:
            warning_counts[warning] = warning_counts.get(warning, 0) + 1

        # Data quality metrics
        has_analyst = sum(1 for r in self.results if r.has_analyst_growth)
        has_historical = sum(1 for r in self.results if r.has_historical_fcf)
        has_both = sum(
            1 for r in self.results if r.has_analyst_growth and r.has_historical_fcf
        )

        # Validation metrics for successful valuations
        successful_results = [r for r in self.results if r.success]

        # Growth rate statistics
        growth_rates = [
            r.growth_rate_used for r in successful_results if r.growth_rate_used is not None
        ]
        avg_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 0

        # WACC statistics
        waccs = [r.wacc for r in successful_results if r.wacc is not None]
        avg_wacc = sum(waccs) / len(waccs) if waccs else 0

        # Upside statistics
        upsides = [r.upside_pct for r in successful_results if r.upside_pct is not None]
        avg_upside = sum(upsides) / len(upsides) if upsides else 0

        # Sector-level performance
        sector_stats = {}
        for sector in STRESS_TEST_STOCKS.keys():
            sector_results = [r for r in self.results if r.sector == sector]
            sector_stats[sector] = {
                "total": len(sector_results),
                "successful": sum(1 for r in sector_results if r.success),
                "failed": sum(1 for r in sector_results if not r.success),
                "success_rate": sum(1 for r in sector_results if r.success)
                / len(sector_results)
                * 100,
            }

        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_stocks": total,
                "successful": successful,
                "failed": failed,
                "success_rate_pct": (successful / total * 100) if total > 0 else 0,
            },
            "error_analysis": {
                "error_types": error_types,
                "most_common_error": max(error_types.items(), key=lambda x: x[1])[0]
                if error_types
                else None,
            },
            "data_dependency": {
                "relies_on_external_growth": relies_on_external,
                "external_dependency_pct": (relies_on_external / total * 100)
                if total > 0
                else 0,
                "calculation_methods": calculation_methods,
            },
            "data_quality": {
                "has_analyst_growth": has_analyst,
                "has_historical_fcf": has_historical,
                "has_both_sources": has_both,
                "analyst_coverage_pct": (has_analyst / total * 100) if total > 0 else 0,
                "historical_data_pct": (has_historical / total * 100) if total > 0 else 0,
            },
            "warnings": {
                "total_warnings": len(all_warnings),
                "unique_warnings": len(warning_counts),
                "warning_frequency": dict(
                    sorted(warning_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                ),
            },
            "valuation_metrics": {
                "avg_growth_rate_pct": avg_growth * 100 if avg_growth else 0,
                "avg_wacc_pct": avg_wacc * 100 if avg_wacc else 0,
                "avg_upside_pct": avg_upside,
                "median_upside_pct": sorted(upsides)[len(upsides) // 2]
                if upsides
                else 0,
            },
            "sector_performance": sector_stats,
            "detailed_results": [asdict(r) for r in self.results],
        }

        return report

    def print_report(self, report: dict[str, Any]) -> None:
        """Print formatted stress test report."""
        print(f"\n{'='*80}")
        print("STRESS TEST REPORT")
        print(f"{'='*80}\n")

        # Summary
        summary = report["summary"]
        print(f"Total Stocks Tested: {summary['total_stocks']}")
        print(f"Successful: {summary['successful']} ({summary['success_rate_pct']:.1f}%)")
        print(f"Failed: {summary['failed']}")

        # Error Analysis
        if report["error_analysis"]["error_types"]:
            print(f"\n{'─'*80}")
            print("ERROR ANALYSIS")
            print(f"{'─'*80}")
            for error_type, count in report["error_analysis"]["error_types"].items():
                print(f"  {error_type}: {count}")

        # Data Dependency
        print(f"\n{'─'*80}")
        print("DATA DEPENDENCY ANALYSIS")
        print(f"{'─'*80}")
        dep = report["data_dependency"]
        print(f"Stocks relying on external growth: {dep['relies_on_external_growth']} ({dep['external_dependency_pct']:.1f}%)")
        print(f"\nCalculation Methods:")
        for method, count in dep["calculation_methods"].items():
            print(f"  {method}: {count}")

        # Data Quality
        print(f"\n{'─'*80}")
        print("DATA QUALITY")
        print(f"{'─'*80}")
        dq = report["data_quality"]
        print(f"Analyst Coverage: {dq['has_analyst_growth']} ({dq['analyst_coverage_pct']:.1f}%)")
        print(f"Historical FCF Data: {dq['has_historical_fcf']} ({dq['historical_data_pct']:.1f}%)")
        print(f"Both Sources: {dq['has_both_sources']}")

        # Warnings
        if report["warnings"]["warning_frequency"]:
            print(f"\n{'─'*80}")
            print("TOP WARNINGS")
            print(f"{'─'*80}")
            for warning, count in list(report["warnings"]["warning_frequency"].items())[:5]:
                print(f"  [{count}x] {warning}")

        # Valuation Metrics
        print(f"\n{'─'*80}")
        print("VALUATION METRICS (Successful Valuations)")
        print(f"{'─'*80}")
        vm = report["valuation_metrics"]
        print(f"Average Growth Rate: {vm['avg_growth_rate_pct']:.2f}%")
        print(f"Average WACC: {vm['avg_wacc_pct']:.2f}%")
        print(f"Average Upside: {vm['avg_upside_pct']:.2f}%")
        print(f"Median Upside: {vm['median_upside_pct']:.2f}%")

        # Sector Performance
        print(f"\n{'─'*80}")
        print("SECTOR PERFORMANCE")
        print(f"{'─'*80}")
        for sector, stats in report["sector_performance"].items():
            print(
                f"  {sector:<25} {stats['successful']}/{stats['total']} ({stats['success_rate']:.0f}%)"
            )

        print(f"\n{'='*80}\n")

    def save_report(self, report: dict[str, Any], filepath: str) -> None:
        """Save report to JSON file."""
        # Convert to JSON-serializable format
        def make_serializable(obj):
            if isinstance(obj, (str, int, float, type(None))):
                return obj
            elif isinstance(obj, bool):
                return obj
            elif isinstance(obj, dict):
                return {k: make_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_serializable(item) for item in obj]
            else:
                return str(obj)
        
        serializable_report = make_serializable(report)
        
        with open(filepath, "w") as f:
            json.dump(serializable_report, f, indent=2)
        print(f"\nDetailed report saved to: {filepath}")


# Main stress test
@pytest.fixture
def stress_tester():
    """Fixture providing stress tester instance."""
    return DCFStressTester()


def test_system_stress_comprehensive(stress_tester):
    """
    Comprehensive stress test of DCF valuation system.

    Tests 50+ stocks across all sectors to validate robustness,
    identify calculation issues, and assess data dependencies.
    """
    # Run all tests
    results = stress_tester.run_all_tests()

    # Generate and print report
    report = stress_tester.generate_report()
    stress_tester.print_report(report)

    # Save detailed report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"data/stress_test_report_{timestamp}.json"
    stress_tester.save_report(report, report_path)

    # Assertions to enforce quality standards
    summary = report["summary"]

    # At least 80% success rate required
    assert (
        summary["success_rate_pct"] >= 80.0
    ), f"Success rate {summary['success_rate_pct']:.1f}% below 80% threshold"

    # No unexpected errors allowed
    unexpected_errors = [
        r for r in results if not r.success and r.error_type not in ["ValidationError"]
    ]
    assert (
        len(unexpected_errors) == 0
    ), f"Found {len(unexpected_errors)} unexpected errors (non-ValidationError)"

    # Maximum 50% external dependency
    external_dep_pct = report["data_dependency"]["external_dependency_pct"]
    assert (
        external_dep_pct <= 50.0
    ), f"External growth dependency {external_dep_pct:.1f}% exceeds 50% threshold"

    # At least 70% should have both analyst and historical data
    both_sources_pct = (
        report["data_quality"]["has_both_sources"] / summary["total_stocks"] * 100
    )
    assert (
        both_sources_pct >= 70.0
    ), f"Only {both_sources_pct:.1f}% have both data sources (need 70%)"

    print("\n✅ All stress test quality checks passed!")


def test_individual_sector_robustness(stress_tester):
    """Test that each sector has robust valuation coverage."""
    results = stress_tester.run_all_tests()
    report = stress_tester.generate_report()

    sector_stats = report["sector_performance"]

    # Each sector should have at least 75% success rate
    failed_sectors = []
    for sector, stats in sector_stats.items():
        if stats["success_rate"] < 75.0:
            failed_sectors.append(f"{sector}: {stats['success_rate']:.1f}%")

    assert (
        len(failed_sectors) == 0
    ), f"Sectors with <75% success rate: {', '.join(failed_sectors)}"


def test_calculation_consistency(stress_tester):
    """Test that calculations are consistent and within reasonable bounds."""
    results = stress_tester.run_all_tests()
    successful = [r for r in results if r.success]

    issues = []

    for result in successful:
        ticker = result.ticker

        # WACC should be reasonable (2% - 20%)
        if result.wacc and (result.wacc < 0.02 or result.wacc > 0.20):
            issues.append(f"{ticker}: WACC {result.wacc:.2%} outside [2%, 20%]")

        # Growth rate should be reasonable (-50% to +100%)
        if result.growth_rate_used and (
            result.growth_rate_used < -0.50 or result.growth_rate_used > 1.00
        ):
            issues.append(
                f"{ticker}: Growth {result.growth_rate_used:.2%} outside [-50%, 100%]"
            )

        # Terminal growth < WACC
        if (
            result.terminal_growth
            and result.wacc
            and result.terminal_growth >= result.wacc
        ):
            issues.append(
                f"{ticker}: Terminal growth {result.terminal_growth:.2%} >= WACC {result.wacc:.2%}"
            )

        # Intrinsic value should be positive
        if result.intrinsic_value and result.intrinsic_value <= 0:
            issues.append(f"{ticker}: Negative/zero intrinsic value")

    assert len(issues) == 0, f"Calculation issues found:\n" + "\n".join(issues)


if __name__ == "__main__":
    # Allow running directly for quick testing
    print("\n🚀 Starting DCF System Stress Test...")
    tester = DCFStressTester()
    results = tester.run_all_tests()
    report = tester.generate_report()
    tester.print_report(report)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"data/stress_test_report_{timestamp}.json"
    tester.save_report(report, report_path)

    print("\n✅ Stress test complete! Review detailed results above.")
