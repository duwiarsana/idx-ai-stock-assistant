"""Stock data API endpoints."""

import logging
from fastapi import APIRouter, HTTPException

from app.services.stock_service import stock_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{ticker}")
async def get_stock(ticker: str):
    """
    Get full stock data for an IDX ticker.

    Example: GET /api/v1/stocks/BBCA
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    data = await stock_service.get_stock_data(ticker)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"Stock {ticker} not found. Ensure it's a valid IDX ticker.",
        )

    return {
        "status": "success",
        "data": data,
    }


@router.get("/{ticker}/quote")
async def get_stock_quote(ticker: str):
    """
    Get quick stock quote (lightweight).

    Example: GET /api/v1/stocks/BBCA/quote
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    quote = await stock_service.get_quick_quote(ticker)
    if not quote:
        raise HTTPException(
            status_code=404,
            detail=f"Stock {ticker} not found.",
        )

    return {
        "status": "success",
        "data": quote,
    }


@router.get("/{ticker}/technicals")
async def get_stock_technicals(ticker: str):
    """
    Get technical indicators for a stock.

    Example: GET /api/v1/stocks/BBCA/technicals
    """
    ticker = ticker.upper().strip()

    data = await stock_service.get_stock_data(ticker)
    if not data:
        raise HTTPException(status_code=404, detail=f"Stock {ticker} not found.")

    return {
        "status": "success",
        "ticker": ticker,
        "technicals": data.get("technicals", {}),
    }
