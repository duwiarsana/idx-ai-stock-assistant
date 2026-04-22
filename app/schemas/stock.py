"""Pydantic schemas for stock data."""

from pydantic import BaseModel, Field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID


class StockBase(BaseModel):
    ticker: str = Field(..., example="BBCA")
    name: str = Field(..., example="Bank Central Asia Tbk")
    sector: Optional[str] = None
    subsector: Optional[str] = None
    board: Optional[str] = None


class StockResponse(StockBase):
    id: UUID
    is_active: bool
    last_updated: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StockPriceResponse(BaseModel):
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    change_pct: Optional[Decimal] = None

    model_config = {"from_attributes": True}


class StockDetailResponse(BaseModel):
    """Full stock detail with recent prices."""
    stock: StockResponse
    current_price: Optional[Decimal] = None
    change_today: Optional[Decimal] = None
    change_pct_today: Optional[Decimal] = None
    volume_today: Optional[int] = None
    high_52w: Optional[Decimal] = None
    low_52w: Optional[Decimal] = None
    avg_volume_20d: Optional[int] = None
    recent_prices: list[StockPriceResponse] = []


class StockQuickLookup(BaseModel):
    """Lightweight stock quote for quick responses."""
    ticker: str
    name: str
    price: Decimal
    change: Decimal
    change_pct: Decimal
    volume: int
    last_updated: datetime
