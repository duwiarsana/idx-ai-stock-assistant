"""Pydantic schemas for watchlists."""

from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID


class WatchlistCreate(BaseModel):
    ticker: str = Field(..., example="BBCA")
    alert_price_above: Optional[Decimal] = None
    alert_price_below: Optional[Decimal] = None
    notes: Optional[str] = Field(None, max_length=500)


class WatchlistResponse(BaseModel):
    id: UUID
    ticker: str
    company_name: str
    alert_price_above: Optional[Decimal] = None
    alert_price_below: Optional[Decimal] = None
    notes: Optional[str] = None
    created_at: datetime
