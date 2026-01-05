"""
Test script to download pilot backtest data.

Downloads 5 stocks over 5 years (2019-2024) to validate data collection infrastructure.
"""

from src.backtest.data_loader import HistoricalDataLoader
from src.logging_config import get_logger

logger = get_logger(__name__)


def main():
    """Download and validate pilot data."""
    logger.info("="*80)
    logger.info("PILOT DATA DOWNLOAD - 5 Stocks, 5 Years (2019-2024)")
    logger.info("="*80)
    
    loader = HistoricalDataLoader()
    
    # Download pilot data
    data = loader.prepare_pilot_data()
    
    # Summary statistics
    logger.info("\n" + "="*80)
    logger.info("DATA SUMMARY")
    logger.info("="*80)
    
    logger.info(f"\nPrice Data: {len(data['prices'])} stocks")
    for ticker, df in data['prices'].items():
        logger.info(f"  {ticker}: {len(df)} records from {df.index.min().date()} to {df.index.max().date()}")
        
    logger.info(f"\nFinancial Data: {len(data['financials'])} stocks")
    for ticker, df in data['financials'].items():
        start_date = df.index.min()
        end_date = df.index.max()
        # Handle both datetime and string formats
        if hasattr(start_date, 'date'):
            start_date = start_date.date()
        if hasattr(end_date, 'date'):
            end_date = end_date.date()
        logger.info(f"  {ticker}: {len(df)} quarters from {start_date} to {end_date}")
        
    logger.info(f"\nMarket Data: {len(data['market_data'])} records")
    
    # Validate forward returns are calculated
    sample_ticker = list(data['prices'].keys())[0]
    sample_df = data['prices'][sample_ticker]
    forward_cols = [col for col in sample_df.columns if col.startswith('returns_')]
    logger.info(f"\nForward return columns calculated: {forward_cols}")
    
    # Check data quality
    logger.info("\n" + "="*80)
    logger.info("DATA QUALITY CHECKS")
    logger.info("="*80)
    
    for ticker, df in data['prices'].items():
        missing_pct = df['close'].isna().sum() / len(df) * 100
        logger.info(f"{ticker}: {missing_pct:.2f}% missing price data")
        
    logger.info("\n✅ Pilot data download complete! Ready for backtesting.")
    

if __name__ == "__main__":
    main()
