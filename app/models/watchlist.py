"""Watchlist model."""

import uuid
from decimal import Decimal
from typing import Optional
from sqlalchemy import ForeignKey, Numeric, String, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class Watchlist(Base, TimestampMixin):
    """User's stock watchlist entry."""

    __tablename__ = "watchlists"
    __table_args__ = (
        Index("ix_watchlists_user_stock", "user_id", "stock_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    stock_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    alert_price_above: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    alert_price_below: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    notes: Mapped[Optional[str]] = mapped_column(String(500))

    # Relationships
    user = relationship("User", back_populates="watchlists")
    stock = relationship("Stock")
