
import logging
import os
import pandas as pd
import mplfinance as mpf
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ChartService:
    """Service to generate stock charts using mplfinance."""

    def __init__(self, output_dir: str = "temp/charts"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    async def generate_candlestick_chart(self, ticker: str, history_data: list) -> Optional[str]:
        """
        Generates a candlestick chart and returns the file path.
        """
        if not history_data:
            logger.warning(f"No history data for {ticker}, cannot generate chart.")
            return None

        try:
            # 1. Convert history data to DataFrame
            df = pd.DataFrame(history_data)
            
            # Map lowercase keys to expected mplfinance columns
            column_map = {
                'date': 'Date',
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            }
            df = df.rename(columns=column_map)
            
            df['Date'] = pd.to_datetime(df['Date'])
            df.set_index('Date', inplace=True)
            
            # Ensure columns are float
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = df[col].astype(float)

            # 2. Configure chart style
            mc = mpf.make_marketcolors(
                up='green', down='red',
                edge='inherit',
                wick='inherit',
                volume='in',
                ohlc='inherit'
            )
            s = mpf.make_mpf_style(marketcolors=mc, gridstyle='--', y_on_right=True)

            # 3. Define output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ticker}_{timestamp}.png"
            filepath = os.path.join(self.output_dir, filename)

            # 4. Plot and save
            # Add Moving Averages
            mpf.plot(
                df,
                type='candle',
                style=s,
                title=f"\n{ticker} Candlestick Chart",
                ylabel='Price (Rp)',
                ylabel_lower='Volume',
                volume=True,
                mav=(20, 50),
                savefig=filepath,
                tight_layout=True,
                figratio=(12, 8)
            )

            logger.info(f"Chart generated for {ticker} at {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Error generating chart for {ticker}: {e}")
            return None

    def cleanup_charts(self):
        """Delete all generated charts in the temp directory."""
        try:
            for f in os.listdir(self.output_dir):
                os.remove(os.path.join(self.output_dir, f))
            logger.info("Temporary charts cleaned up.")
        except Exception as e:
            logger.error(f"Error cleaning up charts: {e}")

# Singleton
chart_service = ChartService()
