"""External data source integrations (FRED, Shiller, Damodaran, XBRL)."""

from src.external.fred import FredConnector, get_fred_connector
from src.external.shiller import (
    get_shiller_data,
    get_current_cape,
    get_equity_risk_scalar,
    display_cape_summary,
)
from src.external.damodaran import (
    DamodaranLoader,
    get_damodaran_loader,
    SectorPriors,
)
from src.external.xbrl_parser import XBRLDirectParser

__all__ = [
    # FRED
    "FredConnector",
    "get_fred_connector",
    # Shiller CAPE
    "get_shiller_data",
    "get_current_cape",
    "get_equity_risk_scalar",
    "display_cape_summary",
    # Damodaran
    "DamodaranLoader",
    "get_damodaran_loader",
    "SectorPriors",
    # XBRL
    "XBRLDirectParser",
]
