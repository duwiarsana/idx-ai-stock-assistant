import asyncio
import logging
import sys

# Add current directory to path
sys.path.append(".")

# Initialize logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger("run_screener_manual")

from app.services.stock_service import stock_service
from app.services.analysis_engine import analyze as run_analysis
from app.scheduler.jobs import ALL_TICKERS

async def main():
    logger.info("Starting manual screener check...")
    results = []
    
    # Check top 15 tickers to keep it reasonably fast
    tickers_to_check = ALL_TICKERS[:15]
    logger.info(f"Scanning tickers: {', '.join(tickers_to_check)}")
    
    for ticker in tickers_to_check:
        try:
            logger.info(f"Processing {ticker}...")
            data = await stock_service.get_stock_data(ticker)
            if not data:
                logger.warning(f"No data fetched for {ticker}")
                continue
                
            history = data.get("history", [])
            analysis = run_analysis(ticker, history)
            if analysis:
                results.append({
                    "Ticker": ticker,
                    "Price": data.get("current_price"),
                    "Score": analysis.final_score,
                    "Signal": analysis.signal,
                    "Trend": analysis.trend_status,
                    "RSI": data.get("technicals", {}).get("rsi_14"),
                })
        except Exception as e:
            logger.error(f"Error checking {ticker}: {e}")
            
    # Sort results by score descending
    results = sorted(results, key=lambda x: x["Score"], reverse=True)
    
    # Print results table
    print("\n" + "="*50)
    print("           IDX STOCK SCREENER RESULTS")
    print("="*50)
    if results:
        headers = results[0].keys()
        rows = [list(r.values()) for r in results]
        # Custom basic print format instead of tabulate if tabulate not installed
        try:
            from tabulate import tabulate
            print(tabulate(rows, headers=headers, tablefmt="grid"))
        except ImportError:
            for r in results:
                print(f"{r['Ticker']}: Price={r['Price']}, Score={r['Score']}, Signal={r['Signal']}, Trend={r['Trend']}, RSI={r['RSI']}")
    else:
        print("No candidates found.")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
