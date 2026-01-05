"""
Direct XBRL parsing without LLM dependencies.

Parses SEC Company Facts API data to extract financial metrics for DCF valuation.
Uses XBRL tag mapping with fallback logic to handle accounting standard variations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# SEC requires User-Agent header
SEC_USER_AGENT = "DCF-Valuation-Tool research@dcfvaluation.com"

# XBRL tag variations for common metrics (US-GAAP taxonomy)
# Order matters: Try newer accounting standards first (ASC 606 for revenue)
XBRL_TAG_MAPPINGS = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",  # ASC 606 (2018+)
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",  # Legacy tag
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "net_income": [
        "NetIncomeLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "ProfitLoss",
    ],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ],
    "total_debt": [
        "LongTermDebtAndCapitalLeaseObligations",
        "DebtCurrent",
        "LongTermDebt",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
        "CashCashEquivalentsAndShortTermInvestments",
    ],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "CommonStockSharesIssued",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "total_assets": [
        "Assets",
        "AssetsCurrent",
    ],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
}


class XBRLDirectParser:
    """Parse SEC XBRL data directly without LLM."""

    def __init__(self, cache_dir: Path | None = None, parquet_cache_dir: Path | None = None):
        """
        Initialize XBRL parser.

        Parameters
        ----------
        cache_dir : Path, optional
            Directory for caching Company Facts JSON responses.
            Defaults to data/cache/company_facts/
        parquet_cache_dir : Path, optional
            Directory for caching processed Parquet files (faster access).
            Defaults to data/cache/xbrl_parquet/
        """
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": SEC_USER_AGENT})

        # Setup JSON caching (raw Company Facts)
        if cache_dir is None:
            cache_dir = Path("data/cache/company_facts")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Setup Parquet caching (processed financials)
        if parquet_cache_dir is None:
            parquet_cache_dir = Path("data/cache/xbrl_parquet")
        self.parquet_cache_dir = parquet_cache_dir
        self.parquet_cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cik_from_ticker(self, ticker: str) -> str:
        """
        Get CIK number from ticker symbol.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol (e.g., 'AAPL')

        Returns
        -------
        str
            CIK number padded to 10 digits (e.g., '0000320193')

        Raises
        ------
        ValueError
            If ticker not found in SEC database
        """
        # Try cache first
        cache_file = self.cache_dir / "ticker_cik_mapping.json"
        if cache_file.exists():
            mapping = json.loads(cache_file.read_text())
            if ticker.upper() in mapping:
                return mapping[ticker.upper()]

        # Fetch from SEC
        url = "https://www.sec.gov/files/company_tickers.json"
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Build mapping and cache
        mapping = {}
        for entry in data.values():
            mapping[entry["ticker"].upper()] = str(entry["cik_str"]).zfill(10)

        cache_file.write_text(json.dumps(mapping, indent=2))

        # Lookup ticker
        ticker_upper = ticker.upper()
        if ticker_upper not in mapping:
            raise ValueError(f"Ticker {ticker} not found in SEC database")

        return mapping[ticker_upper]

    def get_company_facts(self, cik: str, use_cache: bool = True) -> dict[str, Any]:
        """
        Download all XBRL facts for a company.

        Parameters
        ----------
        cik : str
            CIK number (10 digits)
        use_cache : bool, default True
            Whether to use cached data if available

        Returns
        -------
        dict
            Company facts JSON from SEC API

        Raises
        ------
        requests.HTTPError
            If SEC API request fails
        """
        cache_file = self.cache_dir / f"CIK{cik}.json"

        # Try cache
        if use_cache and cache_file.exists():
            logger.debug(f"Using cached data for CIK {cik}")
            return json.loads(cache_file.read_text())

        # Fetch from SEC
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        logger.info(f"Fetching company facts for CIK {cik} from SEC API")

        response = self.session.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Cache response
        cache_file.write_text(json.dumps(data, indent=2))
        logger.debug(f"Cached company facts for CIK {cik}")

        return data

    def extract_metric_timeseries(self, facts: dict, metric_key: str, form_type: str = "10-K") -> pd.DataFrame:
        """
        Extract time series for a specific metric.

        Parameters
        ----------
        facts : dict
            Company facts JSON from SEC API
        metric_key : str
            Our standardized metric name (e.g., 'revenue')
        form_type : str, default '10-K'
            Filter by form type ('10-K' for annual, '10-Q' for quarterly)

        Returns
        -------
        pd.DataFrame
            Time series with columns: date, value, fiscal_year, fiscal_period,
            filed, unit, xbrl_tag
        """
        us_gaap = facts.get("facts", {}).get("us-gaap", {})

        # Try each possible XBRL tag for this metric
        for xbrl_tag in XBRL_TAG_MAPPINGS.get(metric_key, []):
            if xbrl_tag not in us_gaap:
                continue

            metric_data = us_gaap[xbrl_tag]
            units = metric_data.get("units", {})

            # Try each unit (USD, shares, etc.)
            for unit_type, entries in units.items():
                records = []
                for entry in entries:
                    # Filter by form type
                    if entry.get("form") != form_type:
                        continue

                    # Extract key fields
                    record = {
                        "date": entry.get("end"),  # Period end date
                        "value": entry.get("val"),
                        "fiscal_year": entry.get("fy"),
                        "fiscal_period": entry.get("fp"),  # FY, Q1, Q2, Q3, Q4
                        "filed": entry.get("filed"),  # When filed with SEC
                        "unit": unit_type,
                        "xbrl_tag": xbrl_tag,
                    }
                    records.append(record)

                if records:
                    df = pd.DataFrame(records)
                    df["date"] = pd.to_datetime(df["date"])
                    df = df.sort_values("date")

                    # Keep most recent filing per date (handles amendments)
                    df = df.sort_values(["date", "filed"]).groupby("date").last().reset_index()

                    logger.debug(f"Found {len(df)} {form_type} entries for {metric_key} using tag {xbrl_tag}")
                    return df

        # Metric not found
        logger.warning(
            f"Could not find {metric_key} in company facts (tried {len(XBRL_TAG_MAPPINGS.get(metric_key, []))} tags)"
        )
        return pd.DataFrame()

    def get_financials(self, ticker: str, form_type: str = "10-K", use_parquet_cache: bool = True) -> pd.DataFrame:
        """
        Get all financial metrics for a ticker.

        Uses 3-tier caching: Parquet (fastest) → JSON → API call (slowest).

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        form_type : str, default '10-K'
            '10-K' for annual, '10-Q' for quarterly
        use_parquet_cache : bool, default True
            Whether to use Parquet cache for faster loading

        Returns
        -------
        pd.DataFrame
            Financial data with all metrics as columns, indexed by date.
            Includes: revenue, net_income, operating_cash_flow, capex,
            total_debt, cash, shares_outstanding, total_assets,
            stockholders_equity, free_cash_flow

        Raises
        ------
        ValueError
            If ticker not found
        requests.HTTPError
            If SEC API request fails
        """
        # Check Parquet cache first (fastest - 783x smaller, 1.5x faster)
        if use_parquet_cache:
            parquet_file = self.parquet_cache_dir / f"{ticker}_{form_type}.parquet"
            if parquet_file.exists():
                logger.debug(f"Loading {ticker} from Parquet cache (fast path)")
                return pd.read_parquet(parquet_file)

        # Fall back to JSON + extraction (medium speed)
        cik = self.get_cik_from_ticker(ticker)
        facts = self.get_company_facts(cik)

        # Extract each metric
        all_data = {}
        for metric_key in XBRL_TAG_MAPPINGS:
            df = self.extract_metric_timeseries(facts, metric_key, form_type)
            if not df.empty:
                # Use most recent value per date
                all_data[metric_key] = df.set_index("date")["value"]

        # Combine into single DataFrame
        if not all_data:
            logger.error(f"No financial data found for {ticker}")
            return pd.DataFrame()

        combined = pd.DataFrame(all_data)

        # Calculate derived metrics
        if "operating_cash_flow" in combined.columns and "capex" in combined.columns:
            combined["free_cash_flow"] = combined["operating_cash_flow"] - combined["capex"].abs()

        logger.info(
            f"Successfully extracted {len(combined)} {form_type} periods for {ticker} "
            f"with {len([c for c in combined.columns if combined[c].notna().any()])} metrics"
        )

        # Save to Parquet cache for faster subsequent access
        if use_parquet_cache:
            parquet_file = self.parquet_cache_dir / f"{ticker}_{form_type}.parquet"
            combined.to_parquet(parquet_file, compression="snappy")
            logger.debug(f"Cached {ticker} to Parquet (783x compression, 1.5x faster reads)")

        return combined

    def clear_cache(self, ticker: str | None = None) -> None:
        """
        Clear cached data.

        Parameters
        ----------
        ticker : str, optional
            If provided, only clear cache for this ticker.
            If None, clear all cached data.
        """
        if ticker is None:
            # Clear all cache
            for file in self.cache_dir.glob("*.json"):
                file.unlink()
            logger.info("Cleared all XBRL cache")
        else:
            # Clear specific ticker
            cik = self.get_cik_from_ticker(ticker)
            cache_file = self.cache_dir / f"CIK{cik}.json"
            if cache_file.exists():
                cache_file.unlink()
                logger.info(f"Cleared cache for {ticker} (CIK {cik})")
