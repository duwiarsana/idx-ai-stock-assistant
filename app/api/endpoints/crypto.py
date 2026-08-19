"""Crypto scanner API endpoints — status, latest candidates, alerts, config."""

import asyncio
import logging
import time

from fastapi import APIRouter

from app.config import get_settings
from app.services.crypto_scanner import crypto_scanner
from app.services.crypto_alert import ALERT_KEY_PREFIX
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

# Global price cache for dashboard API
_PRICE_CACHE: dict[str, tuple[float, float]] = {}
_PRICE_CACHE_TTL = 60.0  # 60 seconds (longer TTL to reduce API calls)


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


@router.get("/dashboard/potential")
async def crypto_potential_coins(limit: int = 10, min_score: int = 55):
    """Get potential coins to buy - ranked by momentum score."""
    results = crypto_scanner.state.get("last_results", [])
    filtered = [r for r in results if r.get("score", 0) >= min_score]
    sorted_results = sorted(filtered, key=lambda x: x.get("score", 0), reverse=True)[:limit]
    
    # Enrich with TP/SL levels
    enriched = []
    for r in sorted_results:
        levels = r.get("price_levels") or {}
        enriched.append({
            "symbol": r.get("symbol"),
            "display": r.get("display"),
            "score": round(r.get("score", 0), 2),
            "price": r.get("tf_summaries", {}).get("1h", {}).get("price"),
            "trend": r.get("tf_summaries", {}).get("1h", {}).get("trend"),
            "momentum_score": round(r.get("scores", {}).get("momentum", 0), 2),
            "buy_reason": r.get("ai_verdict", {}).get("reason", [])[:3],
            "entry_level": levels.get("entry"),
            "take_profit_1": levels.get("take_profit_1"),
            "take_profit_2": levels.get("take_profit_2"),
            "stop_loss": levels.get("stop_loss"),
            "risk_reward": levels.get("risk_reward"),
            "recommended_allocation": "5-10% of portfolio",
        })
    
    return {
        "status": "success",
        "data": {
            "last_scan_at": crypto_scanner.state.get("last_scan_at"),
            "total_candidates": len(filtered),
            "showing": len(enriched),
            "min_score_filter": min_score,
            "coins": enriched,
        },
    }


@router.get("/dashboard/positions")
async def crypto_positions_summary():
    """Get current open positions and performance summary."""
    from sqlalchemy import select, func, desc
    from app.db.session import async_session_factory
    from app.models.crypto import CryptoPaperPosition
    import httpx
    
    # Fetch current prices from Tokocrypto API with global caching
    async def get_current_price(symbol: str) -> float:
        now = time.time()
        
        # Check cache first
        if symbol in _PRICE_CACHE:
            cached_price, cached_time = _PRICE_CACHE[symbol]
            if now - cached_time < _PRICE_CACHE_TTL:
                return cached_price
        
        try:
            base = symbol.replace("_USDT", "").lower()
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Retry with backoff for rate limiting
                for attempt in range(3):
                    try:
                        response = await client.get(
                            f"https://www.tokocrypto.site/api/v3/ticker/24hr?symbol={base.upper()}USDT"
                        )
                        if response.status_code == 200:
                            data = response.json()
                            price = float(data.get("lastPrice", 0))
                            if price > 0:
                                _PRICE_CACHE[symbol] = (price, now)
                                return price
                        elif response.status_code == 429:
                            if attempt < 2:
                                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                                continue
                    except httpx.TimeoutException:
                        if attempt < 2:
                            await asyncio.sleep(1)
                            continue
        except Exception as e:
            logger.warning(f"Failed to fetch price for {symbol}: {e}")
        
        # Fallback: return last cached price even if expired
        if symbol in _PRICE_CACHE:
            return _PRICE_CACHE[symbol][0]
        
        return 0
    
    async with async_session_factory() as session:
        # Open positions
        result = await session.execute(
            select(CryptoPaperPosition)
            .where(CryptoPaperPosition.status == "OPEN")
            .order_by(desc(CryptoPaperPosition.created_at))
        )
        open_positions = result.scalars().all()
        
        # Recent closed positions (last 20)
        result = await session.execute(
            select(CryptoPaperPosition)
            .where(CryptoPaperPosition.status == "CLOSED")
            .order_by(desc(CryptoPaperPosition.closed_at))
            .limit(20)
        )
        closed_positions = result.scalars().all()
        
        # Performance stats by mode
        from sqlalchemy import case
        
        stats_result = await session.execute(
            select(
                CryptoPaperPosition.mode,
                func.count().label("total"),
                func.sum(case((CryptoPaperPosition.status == "OPEN", 1), else_=0)).label("open_count"),
                func.sum(case((CryptoPaperPosition.realized_pnl > 0, 1), else_=0)).label("wins"),
                func.sum(case((CryptoPaperPosition.realized_pnl < 0, 1), else_=0)).label("losses"),
                func.sum(CryptoPaperPosition.realized_pnl).label("total_pnl"),
                func.avg(CryptoPaperPosition.realized_pnl).label("avg_pnl"),
            )
            .group_by(CryptoPaperPosition.mode)
        )
        stats = result.scalars().all()
        
        # Enrich open positions with current prices and unrealized PnL
        open_data = []
        for p in open_positions:
            current_price = await get_current_price(p.symbol)
            unrealized_pnl = 0
            unrealized_pnl_pct = 0
            if current_price > 0 and p.entry_price > 0:
                unrealized_pnl = (current_price - p.entry_price) * p.quantity
                unrealized_pnl_pct = ((current_price - p.entry_price) / p.entry_price) * 100
            
            open_data.append({
                "symbol": p.symbol,
                "display": p.display,
                "mode": p.mode,
                "entry_price": round(p.entry_price, 6),
                "current_price": round(current_price, 6) if current_price > 0 else None,
                "quantity": round(p.quantity, 4),
                "invested": round(p.invested, 2),
                "unrealized_pnl": round(unrealized_pnl, 4),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                "take_profit_1": round(p.take_profit_1, 6) if p.take_profit_1 else None,
                "take_profit_2": round(p.take_profit_2, 6) if p.take_profit_2 else None,
                "stop_loss": round(p.stop_loss, 6) if p.stop_loss else None,
                "entry_score": round(p.entry_score, 2) if p.entry_score else None,
                "entry_reason": p.entry_reason,
                "opened_at": p.created_at.isoformat() if p.created_at else None,
            })
        
        closed_data = [
            {
                "symbol": p.symbol,
                "display": p.display,
                "mode": p.mode,
                "entry_price": round(p.entry_price, 6),
                "exit_price": round(p.exit_price, 6) if p.exit_price else None,
                "pnl": round(p.realized_pnl, 4) if p.realized_pnl is not None else 0.0,
                "pnl_pct": round((p.realized_pnl / p.invested * 100), 2) if p.realized_pnl and p.invested and p.invested > 0 else None,
                "exit_reason": p.exit_reason,
                "entry_date": p.created_at.strftime("%Y-%m-%d") if p.created_at else None,
                "exit_date": p.closed_at.strftime("%Y-%m-%d %H:%M") if p.closed_at else None,
            }
            for p in closed_positions
        ]
        
        stats_data = [
            {
                "mode": s.mode,
                "total_trades": s.total,
                "open_positions": s.open_count,
                "wins": s.wins,
                "losses": s.losses,
                "win_rate": round((s.wins / s.total * 100), 1) if s.total and s.total > 0 else 0,
                "total_pnl": round(s.total_pnl, 2) if s.total_pnl else 0,
                "avg_pnl": round(s.avg_pnl, 4) if s.avg_pnl else 0,
            }
            for s in stats
        ]
    
    return {
        "status": "success",
        "data": {
            "open_positions": open_data,
            "closed_positions": closed_data,
            "performance_stats": stats_data,
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


@router.get("/dashboard")
async def crypto_dashboard_html():
    """Serve the crypto trading dashboard HTML page."""
    from fastapi.responses import HTMLResponse
    from pathlib import Path
    
    template_path = Path(__file__).parent.parent.parent / "templates" / "crypto_dashboard.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text())
    return HTMLResponse(content="<h1>Dashboard template not found</h1>", status_code=500)
