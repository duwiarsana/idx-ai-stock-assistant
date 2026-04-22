"""Stock and StockPrice models."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    String, Boolean, Date, Numeric, BigInteger, DateTime, ForeignKey, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Stock(Base, TimestampMixin):
    """Indonesian stock (IDX listed company)."""

    __tablename__ = "stocks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(
        String(10), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subsector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    board: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    last_updated: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    prices = relationship("StockPrice", back_populates="stock", lazy="selectin")
    scores = relationship("StockScore", back_populates="stock", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Stock(ticker={self.ticker}, name={self.name})>"


class StockPrice(Base):
    """Daily OHLCV price record for a stock."""

    __tablename__ = "stock_prices"
    __table_args__ = (
        Index("ix_stock_prices_stock_date", "stock_id", "trade_date", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    stock_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    stock = relationship("Stock", back_populates="prices")

    def __repr__(self) -> str:
        return f"<StockPrice(stock_id={self.stock_id}, date={self.trade_date}, close={self.close})>"


class StockScore(Base):
    """Multi-factor scoring for a stock (Phase 2+)."""

    __tablename__ = "stock_scores"
    __table_args__ = (
        Index("ix_stock_scores_stock_date", "stock_id", "score_date", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    stock_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    score_date: Mapped[date] = mapped_column(Date, nullable=False)
    fundamental_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    technical_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    volume_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    sentiment_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    composite_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    score_details: Mapped[Optional[dict]] = mapped_column(default=None)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    stock = relationship("Stock", back_populates="scores")
