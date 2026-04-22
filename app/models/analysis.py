"""Analysis history model."""

import uuid
from typing import Optional
from sqlalchemy import ForeignKey, Text, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from app.models.base import Base


class AnalysisHistory(Base):
    """Record of AI analysis requests and responses."""

    __tablename__ = "analysis_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    ai_response: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column("metadata", JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="analysis_history")
    stock = relationship("Stock")
