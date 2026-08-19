"""Crypto scanner persistence models (Tokocrypto).

Stores per-scan snapshots and sent alerts so that future performance evaluation
(price 15m/1h/4h/24h after alert) can be added on top without schema churn.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class CryptoScan(Base, TimestampMixin):
    """One analysed candidate within a scan cycle."""

    __tablename__ = "crypto_scans"
    __table_args__ = (
        Index("ix_crypto_scans_symbol_time", "symbol", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), index=True, nullable=False)  # e.g. BTC_USDT
    display: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)   # e.g. BTC/USDT
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # {1h: .., 4h: .., 24h: ..}
    market_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # per-timeframe indicator summaries
    indicator_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # momentum component breakdown
    score_breakdown: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # AI verdict snapshot (verdict/confidence/risk/reason/warning)
    ai_verdict: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CryptoPaperAccount(Base, TimestampMixin):
    """Virtual balance for one quote asset in the paper-trading account."""

    __tablename__ = "crypto_paper_accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    quote_asset: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # USDT / IDR
    initial_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cash_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winning_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CryptoPaperPosition(Base, TimestampMixin):
    """An open (or closed) paper-trading position."""

    __tablename__ = "crypto_paper_positions"
    __table_args__ = (
        Index("ix_paper_positions_status", "status"),
        Index("ix_paper_positions_symbol_status", "symbol", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)      # e.g. BTC_USDT
    base: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    quote: Mapped[str] = mapped_column(String(10), nullable=False)       # e.g. USDT
    display: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")  # OPEN / CLOSED
    # Which engine owns this position: "PAPER" (simulated) or "REAL" (live order).
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="PAPER", index=True)

    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    invested: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # quote amount spent
    take_profit_1: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit_2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # snapshot of the candidate state that led to the entry
    entry_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Trailing stop state (persisted to survive restarts)
    highest_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    atr_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # TP1 / TP2 / SL / MANUAL
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CryptoPaperTrade(Base, TimestampMixin):
    """A single paper fill (BUY / SELL_TP1 / SELL_TP2 / SELL_SL)."""

    __tablename__ = "crypto_paper_trades"
    __table_args__ = (
        Index("ix_paper_trades_position", "position_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    position_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    side: Mapped[str] = mapped_column(String(20), nullable=False)  # BUY / SELL_TP1 / SELL_TP2 / SELL_SL
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quote_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CryptoAlert(Base, TimestampMixin):
    """A Telegram alert that was sent for a candidate."""

    __tablename__ = "crypto_alerts"
    __table_args__ = (
        Index("ix_crypto_alerts_symbol_time", "symbol", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    display: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_confidence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # list of human-readable reasons
    reason: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # telegram delivery status: "sent", "dry-run", or error message
    delivery_status: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
