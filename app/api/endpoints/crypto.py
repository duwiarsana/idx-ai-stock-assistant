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
        if "ALL" in _PRICE_CACHE:
            cached_prices, cached_time = _PRICE_CACHE["ALL"]
            if now - cached_time < _PRICE_CACHE_TTL:
                base = symbol.replace("_USDT", "").upper() + "USDT"
                return cached_prices.get(base, 0.0)
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for attempt in range(3):
                    try:
                        response = await client.get("https://www.tokocrypto.site/api/v3/ticker/price")
                        if response.status_code == 200:
                            data = response.json()
                            # data is a list: [{"symbol": "BTCUSDT", "price": "60000.00"}, ...]
                            prices = {item["symbol"]: float(item["price"]) for item in data}
                            _PRICE_CACHE["ALL"] = (prices, now)
                            base = symbol.replace("_USDT", "").upper() + "USDT"
                            return prices.get(base, 0.0)
                        elif response.status_code == 429:
                            if attempt < 2:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            else:
                                break
                    except Exception as exc:
                        if attempt < 2:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        logger.warning(f"Failed to fetch bulk prices: {exc}")
                        break
        except Exception as e:
            logger.warning(f"Failed to query Tokocrypto: {e}")

        # Fallback to Binance Vision ticker if Tokocrypto fails or is rate-limited (429)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://data-api.binance.vision/api/v3/ticker/price")
                if response.status_code == 200:
                    data = response.json()
                    prices = {item["symbol"]: float(item["price"]) for item in data}
                    _PRICE_CACHE["ALL"] = (prices, now)
                    base = symbol.replace("_USDT", "").upper() + "USDT"
                    return prices.get(base, 0.0)
        except Exception as e:
            logger.warning(f"Error in Binance Vision fallback price client: {e}")
            
        return 0.0
    
    async with async_session_factory() as session:
        # Open positions (REAL mode only)
        result = await session.execute(
            select(CryptoPaperPosition)
            .where(
                CryptoPaperPosition.status == "OPEN",
                CryptoPaperPosition.mode == "REAL"
            )
            .order_by(desc(CryptoPaperPosition.created_at))
        )
        open_positions = result.scalars().all()
        
        # Recent closed positions (last 20, REAL mode only)
        result = await session.execute(
            select(CryptoPaperPosition)
            .where(
                CryptoPaperPosition.status == "CLOSED",
                CryptoPaperPosition.mode == "REAL"
            )
            .order_by(desc(CryptoPaperPosition.closed_at))
            .limit(20)
        )
        closed_positions = result.scalars().all()
        
        # Performance stats by mode (closed trades only)
        from sqlalchemy import case

        stats_result = await session.execute(
            select(
                CryptoPaperPosition.mode,
                func.count().label("total"),
                func.sum(case((CryptoPaperPosition.realized_pnl > 0, 1), else_=0)).label("wins"),
                func.sum(case((CryptoPaperPosition.realized_pnl < 0, 1), else_=0)).label("losses"),
                func.coalesce(func.sum(CryptoPaperPosition.realized_pnl), 0.0).label("total_pnl"),
                func.avg(CryptoPaperPosition.realized_pnl).label("avg_pnl"),
            )
            .where(
                CryptoPaperPosition.status == "CLOSED",
                CryptoPaperPosition.mode == "REAL"
            )
            .group_by(CryptoPaperPosition.mode)
        )
        # NOTE: use stats_result (fresh execute) — re-reading `result` after
        # scalars().all() returns an exhausted cursor (this zeroed all stats).
        stats_rows = stats_result.all()

        # Count open positions per mode from data already loaded
        open_count_by_mode: dict = {}
        for p in open_positions:
            open_count_by_mode[p.mode] = open_count_by_mode.get(p.mode, 0) + 1
        
        # Enrich open positions with current prices and unrealized PnL (gross & net after fee)
        open_data = []
        for p in open_positions:
            current_price = await get_current_price(p.symbol)
            unrealized_pnl = 0.0
            unrealized_pnl_pct = 0.0
            est_fee = 0.0
            net_pnl = 0.0
            net_pnl_pct = 0.0
            is_profitable_net = False

            if current_price > 0 and p.entry_price > 0 and p.quantity > 0:
                gross_value = current_price * p.quantity
                unrealized_pnl = gross_value - p.invested
                unrealized_pnl_pct = (unrealized_pnl / p.invested) * 100 if p.invested > 0 else 0.0
                
                # Standard Tokocrypto / Binance taker fee is 0.1% (0.001)
                est_fee = gross_value * 0.001
                net_proceeds = gross_value - est_fee
                net_pnl = net_proceeds - p.invested
                net_pnl_pct = (net_pnl / p.invested) * 100 if p.invested > 0 else 0.0
                is_profitable_net = net_pnl > 0.0

            open_data.append({
                "id": str(p.id),
                "symbol": p.symbol,
                "display": p.display,
                "mode": p.mode,
                "entry_price": round(p.entry_price, 6),
                "current_price": round(current_price, 6) if current_price > 0 else None,
                "quantity": round(p.quantity, 6),
                "invested": round(p.invested, 2),
                "unrealized_pnl": round(unrealized_pnl, 4),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                "estimated_exit_fee": round(est_fee, 4),
                "net_pnl": round(net_pnl, 4),
                "net_pnl_pct": round(net_pnl_pct, 2),
                "is_profitable_net": is_profitable_net,
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
                "open_positions": open_count_by_mode.get(s.mode, 0),
                "wins": int(s.wins or 0),
                "losses": int(s.losses or 0),
                "win_rate": round((s.wins / s.total * 100), 1) if s.total and s.total > 0 else 0,
                "total_pnl": round(s.total_pnl, 2),
                "avg_pnl": round(s.avg_pnl, 4) if s.avg_pnl else 0,
            }
            for s in stats_rows
        ]
        
        # Fetch actual USDT balance from Tokocrypto
        from app.data.tokocrypto_trade_client import TokoCryptoTradeClient
        usdt_balance = 0.0
        try:
            trade_client = TokoCryptoTradeClient()
            balance = await trade_client.get_balance("USDT")
            if balance is not None:
                usdt_balance = float(balance)
        except Exception as e:
            logger.warning(f"Failed to fetch USDT balance: {e}")
            
        return {
            "status": "success",
            "data": {
                "open_positions": open_data,
                "closed_positions": closed_data,
                "stats": stats_data,
                "real_usdt_balance": round(usdt_balance, 2)
            }
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


@router.post("/positions/{position_id}/close")
async def crypto_manual_close_position(position_id: str):
    """Manually close an open crypto position (REAL or PAPER) at current market price."""
    import uuid
    from fastapi import HTTPException
    from sqlalchemy import select
    from app.db.session import async_session_factory
    from app.models.crypto import CryptoPaperPosition, CryptoPaperAccount
    from app.services.crypto_real import real_trader, EXIT_MANUAL as REAL_EXIT_MANUAL
    from app.services.crypto_paper import paper_trader, EXIT_MANUAL as PAPER_EXIT_MANUAL

    try:
        pos_uuid = uuid.UUID(position_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid position ID format")

    async with async_session_factory() as session:
        result = await session.execute(
            select(CryptoPaperPosition).where(
                CryptoPaperPosition.id == pos_uuid,
                CryptoPaperPosition.status == "OPEN",
            )
        )
        pos = result.scalar_one_or_none()
        if not pos:
            raise HTTPException(status_code=404, detail="Open position not found or already closed")

        # Get latest market price
        current_price = 0.0
        try:
            if pos.mode == "REAL":
                current_price = await real_trader.client.get_price(pos.symbol)
            else:
                current_price = await paper_trader.client.get_price(pos.symbol)
        except Exception as e:
            logger.warning(f"Could not fetch current price from exchange for {pos.symbol}: {e}")

        if not current_price or current_price <= 0:
            if pos.symbol in _PRICE_CACHE:
                current_price = _PRICE_CACHE[pos.symbol][0]
            if not current_price or current_price <= 0:
                current_price = pos.entry_price

        # Fetch corresponding account
        acct_res = await session.execute(
            select(CryptoPaperAccount).where(CryptoPaperAccount.quote_asset == pos.quote)
        )
        account = acct_res.scalar_one_or_none()
        if not account:
            account = CryptoPaperAccount(
                quote_asset=pos.quote,
                initial_balance=0.0,
                cash_balance=0.0,
            )
            session.add(account)
            await session.flush()

        mode = pos.mode
        symbol = pos.symbol
        display = pos.display or pos.symbol

        if mode == "REAL":
            closed = await real_trader._close_position(
                session, pos, account, REAL_EXIT_MANUAL, current_price
            )
            if not closed:
                await session.rollback()
                raise HTTPException(
                    status_code=500,
                    detail=f"Gagal melakukan eksekusi sell REAL di exchange untuk {symbol}",
                )
        else:
            await paper_trader._close_position(
                session, pos, account, PAPER_EXIT_MANUAL, current_price
            )

        await session.commit()

    logger.info(f"Manual close executed successfully for {symbol} ({mode}) @ {current_price}")
    return {
        "status": "success",
        "message": f"Posisi {display} ({mode}) berhasil di-close manual pada harga {current_price}",
        "data": {
            "position_id": position_id,
            "symbol": symbol,
            "mode": mode,
            "exit_price": current_price,
            "realized_pnl": pos.realized_pnl,
        },
    }


@router.get("/klines/{symbol}")
async def get_klines(symbol: str, interval: str = "15m", limit: int = 200):
    """Return OHLCV candlestick data for a symbol.

    Used by the dashboard chart modal. Cached for 30 s per (symbol, interval).
    Symbol should be in raw Tokocrypto format with underscore, e.g. SPYB_USDT.
    """
    from app.data.tokocrypto_client import tokocrypto_client

    cache_key = f"klines:{symbol}:{interval}:{limit}"
    cached = await cache_service._get(cache_key)
    if cached:
        return {"status": "success", "data": cached}

    try:
        # Normalize: accept both SPYB_USDT and SPYBUSDT (no underscore)
        raw_sym = symbol if "_" in symbol else None
        symbols = await tokocrypto_client.fetch_symbols()
        sym_obj = None
        for s in symbols:
            if s.raw_symbol == raw_sym or s.normalized_symbol == symbol.upper().replace("_", ""):
                sym_obj = s
                break
        if sym_obj is None:
            return {"status": "error", "message": f"Symbol {symbol} not found on Tokocrypto"}

        candles = await tokocrypto_client.fetch_klines(sym_obj, interval=interval, limit=limit)
        payload = {"symbol": symbol, "interval": interval, "candles": candles}
        await cache_service._set(cache_key, payload, ttl=30)
        return {"status": "success", "data": payload}
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}
    except Exception as exc:
        logger.warning(f"klines error for {symbol}: {exc}")
        return {"status": "error", "message": f"Failed to fetch klines: {exc}"}


@router.get("/dashboard")
async def crypto_dashboard_html():
    """Serve the crypto trading dashboard HTML page."""
    from fastapi.responses import HTMLResponse
    from pathlib import Path

    template_path = Path(__file__).parent.parent.parent / "templates" / "crypto_dashboard.html"
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text())
    return HTMLResponse(content="<h1>Dashboard template not found</h1>", status_code=500)

