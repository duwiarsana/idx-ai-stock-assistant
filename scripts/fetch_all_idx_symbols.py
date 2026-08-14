import asyncio
import logging
import os
import sys
import requests
import pandas as pd
from sqlalchemy import select

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import async_session_factory
from app.models.stock import Stock

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger("fetch_all_idx_symbols")

def get_wikipedia_symbols():
    logger.info("Fetching listed companies from Wikipedia...")
    url = "https://id.wikipedia.org/wiki/Daftar_perusahaan_yang_tercatat_di_Bursa_Efek_Indonesia"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    
    from io import StringIO
    # Read tables
    dfs = pd.read_html(StringIO(r.text))
    logger.info(f"Found {len(dfs)} tables on the Wikipedia page.")
    
    symbols_list = []
    
    # Usually the tables are grouped alphabetically or in multiple tables
    for df in dfs:
        # Check if table has a column representing Code/Ticker
        # Wikipedia table columns typically: 'Kode', 'Nama Perusahaan', 'Tanggal Pencatatan', dll.
        code_col = None
        for col in df.columns:
            if str(col).strip().lower() in ('kode', 'kode emiten', 'ticker'):
                code_col = col
                break
                
        if code_col is not None:
            name_col = None
            for col in df.columns:
                if 'nama' in str(col).strip().lower():
                    name_col = col
                    break
            
            sector_col = None
            for col in df.columns:
                if 'sektor' in str(col).strip().lower() or 'industri' in str(col).strip().lower():
                    sector_col = col
                    break
            
            for _, row in df.iterrows():
                ticker = str(row[code_col]).strip().upper()
                if "BEI:" in ticker:
                    ticker = ticker.replace("BEI:", "").strip()
                # IDX tickers are usually 4 characters
                if ticker and len(ticker) == 4 and ticker.isalpha():
                    name = str(row[name_col]).strip() if name_col is not None else ""
                    sector = str(row[sector_col]).strip() if sector_col is not None else "General"
                    symbols_list.append({
                        "ticker": ticker,
                        "name": name,
                        "sector": sector,
                        "board": "Main Board"
                    })
                    
    logger.info(f"Extracted {len(symbols_list)} valid IDX tickers.")
    return symbols_list

async def save_symbols(symbols):
    async with async_session_factory() as session:
        inserted = 0
        skipped = 0
        
        for symbol in symbols:
            # Check if exists
            result = await session.execute(
                select(Stock).where(Stock.ticker == symbol["ticker"])
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update name or sector if empty
                if not existing.name and symbol["name"]:
                    existing.name = symbol["name"]
                if existing.sector == "General" and symbol["sector"] != "General":
                    existing.sector = symbol["sector"]
                skipped += 1
                continue
                
            stock = Stock(**symbol)
            session.add(stock)
            inserted += 1
            
        await session.commit()
        logger.info(f"Database update complete: Seeded {inserted} new stocks, updated/skipped {skipped} existing.")

async def main():
    try:
        symbols = get_wikipedia_symbols()
        if not symbols:
            logger.error("No symbols extracted!")
            return
        await save_symbols(symbols)
    except Exception as e:
        logger.error(f"Error during symbol fetch: {e}")

if __name__ == "__main__":
    asyncio.run(main())
