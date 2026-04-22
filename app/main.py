"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.router import api_router

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("🚀 IDX AI Stock Assistant starting up...")
    logger.info(f"   Environment: {settings.app_env}")
    logger.info(f"   LLM Provider: {settings.llm_provider}")
    logger.info(f"   Debug: {settings.debug}")
    yield
    logger.info("🛑 IDX AI Stock Assistant shutting down...")


app = FastAPI(
    title=settings.app_name,
    description=(
        "AI-powered Indonesian stock market analysis assistant. "
        "Provides data-driven insights and analysis for IDX stocks."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)
