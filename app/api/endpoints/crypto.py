"""Crypto scanner API endpoints — status, latest candidates, alerts, config."""

import logging

from fastapi import APIRouter

from app.config import get_settings
from app.services.crypto_scanner import crypto_scanner
from app.services.crypto_alert import ALERT_KEY_PREFIX
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/scanner/status")
async def crypto_scanner_status():
    """Scanner runtime status: last scan, counters, and health."""
    return {
        "status": "success",
        "data": {
            "enabled": settings.crypto_scanner_enabled,
            "dry_run": settings.crypto_scanner_dry_run,
            "interval_minutes": settings.crypto_scan_interval_minutes,
            "last_scan_at": crypto_scanner.state.get("last_scan_at"),
            "last_scan_status": crypto_scanner.state.get("last_scan_status"),
            "last_error": crypto_scanner.state.get("last_error"),
            "pairs_found": crypto_scanner.state.get("pairs_found"),
            "pairs_analysed": crypto_scanner.state.get("pairs_analysed"),
        },
    }


@router.get("/scanner/latest")
async def crypto_scanner_latest(limit: int = 10):
    """Latest scored candidates from the most recent scan."""
    results = crypto_scanner.state.get("last_results", [])[: max(1, min(limit, 50))]
    return {
        "status": "success",
        "data": {
            "last_scan_at": crypto_scanner.state.get("last_scan_at"),
            "count": len(results),
            "results": results,
        },
    }


@router.get("/scanner/config")
async def crypto_scanner_config():
    """Expose scanner configuration (safe subset — no secrets)."""
    return {
        "status": "success",
        "data": {
            "enabled": settings.crypto_scanner_enabled,
            "dry_run": settings.crypto_scanner_dry_run,
            "scan_interval_minutes": settings.crypto_scan_interval_minutes,
            "quote_assets": [q.strip() for q in (settings.crypto_quote_assets or "USDT").split(",") if q.strip()],
            "min_quote_volume": settings.crypto_min_quote_volume or "1_000_000 (default)",
            "min_score_alert": settings.crypto_min_score_alert,
            "max_candidates_ai": settings.crypto_max_candidates_ai,
            "max_alerts_per_scan": settings.crypto_max_alerts_per_scan,
            "alert_cooldown_minutes": settings.crypto_alert_cooldown_minutes,
            "timeframes": ["5m", "15m", "1h"],
            "weights": {
                "trend": settings.crypto_weight_trend,
                "momentum": settings.crypto_weight_momentum,
                "volume": settings.crypto_weight_volume,
                "breakout": settings.crypto_weight_breakout,
            },
        },
    }


@router.get("/alerts")
async def crypto_alerts(limit: int = 20):
    """Recent sent alerts persisted in the database."""
    try:
        from sqlalchemy import select, desc
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoAlert

        async with async_session_factory() as session:
            result = await session.execute(
                select(CryptoAlert)
                .order_by(desc(CryptoAlert.created_at))
                .limit(max(1, min(limit, 100)))
            )
            alerts = result.scalars().all()
            data = [
                {
                    "symbol": a.symbol,
                    "display": a.display,
                    "score": a.score,
                    "price": a.price,
                    "ai_confidence": a.ai_confidence,
                    "risk": a.risk,
                    "reason": a.reason,
                    "delivery_status": a.delivery_status,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in alerts
            ]
    except Exception as e:
        logger.warning(f"Failed to load crypto alerts: {e}")
        data = []

    return {"status": "success", "data": data}


@router.get("/cooldowns")
async def crypto_cooldowns():
    """Show currently-cooled-down pairs (anti-spam state)."""
    try:
        keys = []
        async for key in cache_service.redis.scan_iter(match=f"{ALERT_KEY_PREFIX}*"):
            keys.append(key)
        return {"status": "success", "data": keys}
    except Exception as e:
        logger.warning(f"Failed to list cooldowns: {e}")
        return {"status": "success", "data": []}


# ── Paper trading endpoints ──────────────────────────────────────────

@router.get("/paper/status")
async def crypto_paper_status():
    """Paper trading account + cycle status."""
    from app.services.crypto_paper import paper_trader
    data = {
        "enabled": settings.crypto_paper_trading_enabled,
        "quote_asset": settings.crypto_paper_quote_asset,
        "allocation_percent": settings.crypto_paper_allocation_percent,
        "max_positions": settings.crypto_paper_max_positions,
        "entry_score": settings.crypto_paper_entry_score,
        "last_cycle": paper_trader.state,
    }
    try:
        from sqlalchemy import select, func
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperAccount, CryptoPaperPosition

        async with async_session_factory() as session:
            result = await session.execute(select(CryptoPaperAccount))
            accounts = result.scalars().all()
            open_count = await session.execute(
                select(func.count()).select_from(CryptoPaperPosition).where(
                    CryptoPaperPosition.status == "OPEN"
                )
            )
            data["open_positions"] = int(open_count.scalar() or 0)
            data["accounts"] = [
                {
                    "quote_asset": a.quote_asset,
                    "initial_balance": a.initial_balance,
                    "cash_balance": a.cash_balance,
                    "realized_pnl": a.realized_pnl,
                    "total_trades": a.total_trades,
                    "winning_trades": a.winning_trades,
                }
                for a in accounts
            ]
    except Exception as e:
        logger.warning(f"Failed to load paper status: {e}")
    return {"status": "success", "data": data}


@router.get("/paper/positions")
async def crypto_paper_positions(status: str = "OPEN", limit: int = 20):
    """Paper trading positions (default: open ones)."""
    try:
        from sqlalchemy import select, desc
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperPosition

        async with async_session_factory() as session:
            query = select(CryptoPaperPosition)
            if status and status.upper() in ("OPEN", "CLOSED"):
                query = query.where(CryptoPaperPosition.status == status.upper())
            result = await session.execute(
                query.order_by(desc(CryptoPaperPosition.created_at)).limit(max(1, min(limit, 100)))
            )
            positions = result.scalars().all()
            data = [
                {
                    "id": str(p.id),
                    "symbol": p.symbol,
                    "display": p.display,
                    "quote": p.quote,
                    "status": p.status,
                    "entry_price": p.entry_price,
                    "quantity": p.quantity,
                    "invested": p.invested,
                    "take_profit_1": p.take_profit_1,
                    "take_profit_2": p.take_profit_2,
                    "stop_loss": p.stop_loss,
                    "entry_score": p.entry_score,
                    "exit_price": p.exit_price,
                    "exit_reason": p.exit_reason,
                    "realized_pnl": p.realized_pnl,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                }
                for p in positions
            ]
    except Exception as e:
        logger.warning(f"Failed to load paper positions: {e}")
        data = []
    return {"status": "success", "data": data}


@router.get("/paper/history")
async def crypto_paper_history(limit: int = 20):
    """Recent paper trade fills."""
    try:
        from sqlalchemy import select, desc
        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperTrade

        async with async_session_factory() as session:
            result = await session.execute(
                select(CryptoPaperTrade)
                .order_by(desc(CryptoPaperTrade.created_at))
                .limit(max(1, min(limit, 100)))
            )
            trades = result.scalars().all()
            data = [
                {
                    "position_id": str(t.position_id),
                    "symbol": t.symbol,
                    "side": t.side,
                    "price": t.price,
                    "quantity": t.quantity,
                    "quote_amount": t.quote_amount,
                    "realized_pnl": t.realized_pnl,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                }
                for t in trades
            ]
    except Exception as e:
        logger.warning(f"Failed to load paper history: {e}")
        data = []
    return {"status": "success", "data": data}
