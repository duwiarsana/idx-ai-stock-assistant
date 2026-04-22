"""AI Analysis API endpoints."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)
router = APIRouter()


class AnalyzeRequest(BaseModel):
    question: Optional[str] = Field(
        None,
        max_length=500,
        example="Bagaimana kondisi saham ini untuk jangka menengah?"
    )


@router.get("/{ticker}")
async def analyze_stock(ticker: str, question: Optional[str] = None):
    """
    Get AI-powered analysis for a stock.

    Example: GET /api/v1/analysis/BBCA
    Example: GET /api/v1/analysis/BBCA?question=Bagaimana tren harga?
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    result = await ai_service.analyze_stock(ticker, user_question=question)
    return {
        "status": "success",
        "data": result,
    }


@router.post("/{ticker}")
async def analyze_stock_with_question(ticker: str, body: AnalyzeRequest):
    """
    Get AI-powered analysis with a specific question.

    Example: POST /api/v1/analysis/BBCA
    Body: {"question": "Bagaimana prospek dividen?"}
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    result = await ai_service.analyze_stock(ticker, user_question=body.question)
    return {
        "status": "success",
        "data": result,
    }


@router.get("/{ticker}/quick")
async def quick_lookup(ticker: str):
    """
    Quick stock lookup with brief info (no AI, faster).

    Example: GET /api/v1/analysis/BBCA/quick
    """
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        raise HTTPException(status_code=400, detail="Invalid ticker format")

    result = await ai_service.quick_lookup(ticker)
    return {
        "status": "success",
        "data": {"text": result},
    }
