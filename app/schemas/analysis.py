"""Pydantic schemas for analysis."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from uuid import UUID


class AnalysisRequest(BaseModel):
    """Request for AI stock analysis."""
    ticker: str = Field(..., example="BBCA", min_length=1, max_length=10)
    question: Optional[str] = Field(
        None,
        example="Bagaimana kondisi saham ini?",
        max_length=500,
    )


class AnalysisResponse(BaseModel):
    """AI analysis result."""
    ticker: str
    company_name: str
    analysis: str
    data_summary: dict
    disclaimer: str = (
        "⚠️ Ini bukan saran investasi. "
        "Lakukan riset mandiri sebelum mengambil keputusan."
    )
    generated_at: datetime


class AnalysisHistoryResponse(BaseModel):
    """Stored analysis history entry."""
    id: UUID
    ticker: str
    query: str
    ai_response: str
    created_at: datetime

    model_config = {"from_attributes": True}
