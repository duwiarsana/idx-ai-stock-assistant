"""ML Prediction model — stores predictions and outcomes for model improvement."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String, Date, Numeric, DateTime, ForeignKey, Index, JSON, Float, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class MLPredictionRecord(Base):
    """Stores ML predictions and their actual outcomes for model improvement."""

    __tablename__ = "ml_predictions"
    __table_args__ = (
        Index("ix_ml_predictions_ticker_date", "ticker", "prediction_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Features snapshot (for retraining)
    features: Mapped[Optional[dict]] = mapped_column(JSON, default=None, nullable=True)

    # Prediction
    predicted_direction: Mapped[str] = mapped_column(String(10), nullable=False)  # "UP" / "DOWN"
    predicted_probability: Mapped[float] = mapped_column(Float, nullable=False)
    technical_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    combined_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Actual outcome (filled after PREDICTION_HORIZON days)
    actual_direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    actual_return_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    outcome_filled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Meta
    model_accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
