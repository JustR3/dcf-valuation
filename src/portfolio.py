"""DCF-Aware Portfolio Optimization

Portfolio optimizer that uses DCF valuation results (upside %, conviction)
to create Black-Litterman views for Bayesian portfolio construction.

Features:
- Conviction-based view weighting (HIGH/MODERATE/SPECULATIVE)
- Monte Carlo probability as confidence weights
- Automatic filtering of HOLD/PASS stocks
- Integration with mean-variance optimization
"""

import numpy as np
import pandas as pd
from pypfopt import EfficientFrontier, black_litterman, risk_models

from src.config import config
from src.optimizer import OptimizationMethod, PortfolioEngine, PortfolioMetrics


class DCFPortfolioOptimizer(PortfolioEngine):
    """Portfolio optimizer with DCF-based views via Black-Litterman."""

    def optimize_with_dcf_views(
        self,
        dcf_results: dict[str, dict],
        confidence: float = 0.3,
        method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
        weight_bounds: tuple[float, float] = (0, 1)
    ) -> PortfolioMetrics | None:
        """
        Optimize using Black-Litterman with DCF valuations as views.

        Uses Monte Carlo probabilities as confidence weights and filters by conviction.

        Args:
            dcf_results: Dict of {ticker: enriched_dcf_result}
            confidence: Base view confidence (0-1)
            method: Optimization objective
            weight_bounds: Min/max weight per asset

        Returns:
            PortfolioMetrics or None if optimization fails
        """
        try:
            if self.prices is None:
                self._last_error = "No price data"
                return None

            # Build views with conviction-based filtering FIRST
            viewdict = {}
            view_confidences = []
            viable_tickers = []

            for ticker in self.tickers:
                if ticker not in dcf_results:
                    continue

                dcf = dcf_results[ticker]

                # Skip if no positive value
                if dcf.get('value_per_share', 0) <= 0:
                    continue

                # CRITICAL FIX: Annualize multi-year DCF upside to get expected annual return
                # DCF upside is typically 5-year target, not 1-year return
                # Example: +100% over 5 years = (1+1.0)^(1/5) - 1 = 14.87% annualized
                total_upside = dcf['upside_downside'] / 100.0
                dcf_years = dcf.get('inputs', {}).get('years', 5)  # Default 5-year DCF
                
                # Annualize: (1 + total_return)^(1/years) - 1
                if total_upside > -0.99:  # Prevent math domain error
                    annual_return = (1 + total_upside) ** (1 / dcf_years) - 1
                else:
                    annual_return = total_upside / dcf_years  # Fallback for extreme negatives
                
                conviction_data = dcf.get('conviction', {})
                conviction = conviction_data.get('label', 'N/A')
                mc_data = dcf.get('monte_carlo', {})
                mc_probability = mc_data.get('probability', 0) if mc_data else 0

                # Conviction-based filtering and discounting
                if conviction == 'HIGH CONVICTION':
                    viewdict[ticker] = annual_return
                    view_confidences.append(0.3 + (mc_probability / 100) * 0.3)
                    viable_tickers.append(ticker)

                elif conviction == 'MODERATE':
                    viewdict[ticker] = annual_return
                    view_confidences.append(0.2 + (mc_probability / 100) * 0.2)
                    viable_tickers.append(ticker)

                elif conviction == 'SPECULATIVE':
                    viewdict[ticker] = annual_return * 0.5
                    view_confidences.append(0.1 + (mc_probability / 100) * 0.1)
                    viable_tickers.append(ticker)

                # HOLD/PASS: Exclude entirely

            if not viewdict:
                self._last_error = "No valid DCF results after conviction filtering"
                return None

            if len(viable_tickers) < 2:
                self._last_error = f"Need at least 2 viable stocks after conviction filtering, got {len(viable_tickers)}"
                return None

            # Filter prices to viable tickers only and recalculate matrices
            filtered_prices = self.prices[viable_tickers]

            # Recalculate expected returns and covariance for filtered tickers
            cov_matrix = risk_models.CovarianceShrinkage(filtered_prices).ledoit_wolf()

            # Get market caps for Black-Litterman
            market_caps = pd.Series({
                t: dcf_results.get(t, {}).get('company_data', {}).get('market_cap', 1.0)
                for t in viewdict.keys()
            })

            # Convert to numpy array
            confidences_array = np.array(view_confidences)

            bl = black_litterman.BlackLittermanModel(
                cov_matrix, pi="market", market_caps=market_caps,
                absolute_views=viewdict, omega="idzorek", view_confidences=confidences_array
            )
            bl_returns = bl.bl_returns()

            ef = EfficientFrontier(bl_returns, cov_matrix, weight_bounds=weight_bounds)
            try:
                if method == OptimizationMethod.MAX_SHARPE:
                    ef.max_sharpe(risk_free_rate=self.risk_free_rate)
                elif method == OptimizationMethod.MIN_VOLATILITY:
                    ef.min_volatility()
                else:
                    ef.efficient_risk(target_volatility=0.15)
            except ValueError:
                # If all returns are below risk-free rate, fall back to min volatility
                ef = EfficientFrontier(bl_returns, cov_matrix, weight_bounds=weight_bounds)
                ef.min_volatility()

            weights = {k: v for k, v in ef.clean_weights().items() if v > 0.001}
            perf = ef.portfolio_performance(verbose=False, risk_free_rate=self.risk_free_rate)
            self.optimized_weights = weights

            # Calculate comprehensive risk metrics
            risk_metrics = self.calculate_risk_metrics(weights)

            self.performance = PortfolioMetrics(
                expected_annual_return=perf[0] * 100,
                annual_volatility=perf[1] * 100,
                sharpe_ratio=perf[2],
                weights=weights,
                optimization_method=f"{method.value}_black_litterman",
                sortino_ratio=risk_metrics.get('sortino_ratio'),
                calmar_ratio=risk_metrics.get('calmar_ratio'),
                max_drawdown=risk_metrics.get('max_drawdown'),
                var_95=risk_metrics.get('var_95'),
                cvar_95=risk_metrics.get('cvar_95'),
            )
            return self.performance
        except Exception as e:
            self._last_error = f"Optimization error: {str(e)}"
            return None


def optimize_portfolio_with_dcf(
    dcf_results: dict[str, dict],
    method: OptimizationMethod = OptimizationMethod.MAX_SHARPE,
    period: str = "2y",
    risk_free_rate: float = None,
    confidence: float = 0.3
) -> PortfolioMetrics | None:
    """
    Optimize portfolio using DCF valuations via Black-Litterman.

    Args:
        dcf_results: Dict of {ticker: enriched_dcf_result}
        method: Optimization objective
        period: Historical data period
        risk_free_rate: Risk-free rate (default: from config)
        confidence: View confidence

    Returns:
        PortfolioMetrics or None if fails
    """
    tickers = list(dcf_results.keys())
    if not tickers:
        return None

    if risk_free_rate is None:
        risk_free_rate = config.DEFAULT_RISK_FREE_RATE

    engine = DCFPortfolioOptimizer(tickers=tickers, risk_free_rate=risk_free_rate)
    if not engine.fetch_data(period=period):
        return None
    result = engine.optimize_with_dcf_views(
        dcf_results=dcf_results,
        confidence=confidence,
        method=method
    )
    # Propagate error message if optimization failed
    if result is None and hasattr(engine, '_last_error'):
        # Store error in a way that can be accessed
        pass
    return result
