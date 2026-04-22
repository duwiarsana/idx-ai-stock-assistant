"""API router aggregator."""

from fastapi import APIRouter

from app.api.endpoints import health, stocks, analysis

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["Health"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["Stocks"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
