"""User model for Telegram users."""

import uuid
from typing import Optional
from sqlalchemy import BigInteger, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Telegram user who interacts with the bot."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(
        String(10), default="id", server_default="id"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    # Relationships
    watchlists = relationship("Watchlist", back_populates="user", lazy="selectin")
    analysis_history = relationship(
        "AnalysisHistory", back_populates="user", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"
