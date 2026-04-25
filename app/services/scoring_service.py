"""Scoring service — persists analysis results to database."""

import logging
from datetime import date, datetime
from typing import Optional
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.stock import Stock, StockScore
from app.services.analysis_engine import AnalysisResult

logger = logging.getLogger(__name__)


class ScoringService:
    """Persists analysis scores to the stock_scores table."""

    async def save_score(self, result: AnalysisResult) -> bool:
        """Save an AnalysisResult to the database.

        Parameters
        ----------
        result : AnalysisResult
            The analysis result from the scoring engine.

        Returns
        -------
        True if saved successfully, False otherwise.
        """
        try:
            async with async_session_factory() as session:
                # Find the stock by ticker
                stmt = select(Stock).where(Stock.ticker == result.ticker)
                db_result = await session.execute(stmt)
                stock = db_result.scalar_one_or_none()

                if not stock:
                    logger.warning(f"Stock {result.ticker} not found in DB — cannot save score")
                    return False

                today = date.today()

                # Check if score already exists for today
                existing_stmt = (
                    select(StockScore)
                    .where(StockScore.stock_id == stock.id)
                    .where(StockScore.score_date == today)
                )
                existing = (await session.execute(existing_stmt)).scalar_one_or_none()

                score_details = result.to_dict()

                if existing:
                    # Update existing
                    existing.technical_score = Decimal(str(result.final_score))
                    existing.composite_score = Decimal(str(
                        result.combined_score if result.combined_score else result.final_score
                    ))
                    existing.score_details = score_details
                    existing.calculated_at = datetime.now()
                    logger.debug(f"Updated score for {result.ticker} on {today}")
                else:
                    # Create new
                    score = StockScore(
                        stock_id=stock.id,
                        score_date=today,
                        technical_score=Decimal(str(result.final_score)),
                        composite_score=Decimal(str(
                            result.combined_score if result.combined_score else result.final_score
                        )),
                        score_details=score_details,
                    )
                    session.add(score)
                    logger.debug(f"Saved new score for {result.ticker} on {today}")

                await session.commit()
                return True

        except Exception as e:
            logger.error(f"Error saving score for {result.ticker}: {e}")
            return False

    async def get_latest_scores(self, limit: int = 10) -> list[dict]:
        """Get the latest scored stocks, sorted by composite_score descending.

        Returns
        -------
        List of dicts with ticker, score, signal, confidence info.
        """
        try:
            async with async_session_factory() as session:
                today = date.today()
                stmt = (
                    select(StockScore, Stock)
                    .join(Stock, StockScore.stock_id == Stock.id)
                    .where(StockScore.score_date == today)
                    .order_by(StockScore.composite_score.desc())
                    .limit(limit)
                )
                results = await session.execute(stmt)
                rows = results.all()

                scores = []
                for score, stock in rows:
                    details = score.score_details or {}
                    scores.append({
                        "ticker": stock.ticker,
                        "name": stock.name,
                        "score": float(score.composite_score) if score.composite_score else 0,
                        "signal": details.get("signal", "N/A"),
                        "confidence": details.get("confidence", "N/A"),
                        "trend": details.get("trend_status", "N/A"),
                    })
                return scores

        except Exception as e:
            logger.error(f"Error fetching latest scores: {e}")
            return []


# Singleton
scoring_service = ScoringService()
