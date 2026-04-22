"""Seed script for popular IDX stock tickers.

Populates the stocks table with major Indonesian stocks.
Run: python scripts/seed_tickers.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db.session import async_session_factory
from app.models.stock import Stock

# Major IDX stocks organized by sector
IDX_STOCKS = [
    # Banking
    {"ticker": "BBCA", "name": "Bank Central Asia Tbk", "sector": "Financials", "board": "Main Board"},
    {"ticker": "BBRI", "name": "Bank Rakyat Indonesia Tbk", "sector": "Financials", "board": "Main Board"},
    {"ticker": "BMRI", "name": "Bank Mandiri Tbk", "sector": "Financials", "board": "Main Board"},
    {"ticker": "BBNI", "name": "Bank Negara Indonesia Tbk", "sector": "Financials", "board": "Main Board"},
    {"ticker": "BRIS", "name": "Bank Syariah Indonesia Tbk", "sector": "Financials", "board": "Main Board"},
    {"ticker": "BNGA", "name": "Bank CIMB Niaga Tbk", "sector": "Financials", "board": "Main Board"},
    {"ticker": "BDMN", "name": "Bank Danamon Indonesia Tbk", "sector": "Financials", "board": "Main Board"},

    # Telco
    {"ticker": "TLKM", "name": "Telkom Indonesia Tbk", "sector": "Communication", "board": "Main Board"},
    {"ticker": "EXCL", "name": "XL Axiata Tbk", "sector": "Communication", "board": "Main Board"},
    {"ticker": "ISAT", "name": "Indosat Ooredoo Hutchison Tbk", "sector": "Communication", "board": "Main Board"},

    # Consumer
    {"ticker": "UNVR", "name": "Unilever Indonesia Tbk", "sector": "Consumer", "board": "Main Board"},
    {"ticker": "ICBP", "name": "Indofood CBP Sukses Makmur Tbk", "sector": "Consumer", "board": "Main Board"},
    {"ticker": "INDF", "name": "Indofood Sukses Makmur Tbk", "sector": "Consumer", "board": "Main Board"},
    {"ticker": "MYOR", "name": "Mayora Indah Tbk", "sector": "Consumer", "board": "Main Board"},
    {"ticker": "KLBF", "name": "Kalbe Farma Tbk", "sector": "Healthcare", "board": "Main Board"},

    # Automotive / Industrial
    {"ticker": "ASII", "name": "Astra International Tbk", "sector": "Industrial", "board": "Main Board"},
    {"ticker": "UNTR", "name": "United Tractors Tbk", "sector": "Industrial", "board": "Main Board"},

    # Mining / Energy
    {"ticker": "ADRO", "name": "Adaro Energy Indonesia Tbk", "sector": "Energy", "board": "Main Board"},
    {"ticker": "PTBA", "name": "Bukit Asam Tbk", "sector": "Energy", "board": "Main Board"},
    {"ticker": "ITMG", "name": "Indo Tambangraya Megah Tbk", "sector": "Energy", "board": "Main Board"},
    {"ticker": "ANTM", "name": "Aneka Tambang Tbk", "sector": "Basic Materials", "board": "Main Board"},
    {"ticker": "INCO", "name": "Vale Indonesia Tbk", "sector": "Basic Materials", "board": "Main Board"},

    # Property
    {"ticker": "BSDE", "name": "Bumi Serpong Damai Tbk", "sector": "Property", "board": "Main Board"},
    {"ticker": "CTRA", "name": "Ciputra Development Tbk", "sector": "Property", "board": "Main Board"},

    # Tech
    {"ticker": "GOTO", "name": "GoTo Gojek Tokopedia Tbk", "sector": "Technology", "board": "Main Board"},
    {"ticker": "BUKA", "name": "Bukalapak.com Tbk", "sector": "Technology", "board": "Main Board"},
    {"ticker": "EMTK", "name": "Elang Mahkota Teknologi Tbk", "sector": "Technology", "board": "Main Board"},

    # Retail
    {"ticker": "ACES", "name": "Aspirasi Hidup Indonesia Tbk", "sector": "Consumer Cyclical", "board": "Main Board"},
    {"ticker": "MAPI", "name": "Mitra Adiperkasa Tbk", "sector": "Consumer Cyclical", "board": "Main Board"},

    # Cement / Construction
    {"ticker": "SMGR", "name": "Semen Indonesia Tbk", "sector": "Basic Materials", "board": "Main Board"},
    {"ticker": "WIKA", "name": "Wijaya Karya Tbk", "sector": "Industrial", "board": "Main Board"},
]


async def seed_stocks():
    """Insert stocks into the database if they don't already exist."""
    async with async_session_factory() as session:
        inserted = 0
        skipped = 0

        for stock_data in IDX_STOCKS:
            # Check if already exists
            result = await session.execute(
                select(Stock).where(Stock.ticker == stock_data["ticker"])
            )
            existing = result.scalar_one_or_none()

            if existing:
                skipped += 1
                continue

            stock = Stock(**stock_data)
            session.add(stock)
            inserted += 1

        await session.commit()
        print(f"✅ Seeded {inserted} stocks, skipped {skipped} existing")


if __name__ == "__main__":
    asyncio.run(seed_stocks())
