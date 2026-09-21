"""Crypto Chart Generator for Telegram Bot (/detail <coin>).

Generates high-resolution, dark-themed candlestick charts with EMA indicators,
Volume, and Open Position levels (Entry, TP1, SL) into in-memory PNG bytes.
"""

import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


async def fetch_klines_for_chart(symbol: str, interval: str = "15m", limit: int = 60) -> list[dict]:
    """Fetch candlestick data with fast Binance Vision CDN fallback to Tokocrypto."""
    binance_sym = symbol.upper().replace("_", "").replace("/", "")
    if not (binance_sym.endswith("USDT") or binance_sym.endswith("BIDR") or binance_sym.endswith("IDR")):
        binance_sym += "USDT"

    url = f"https://data-api.binance.vision/api/v3/klines?symbol={binance_sym}&interval={interval}&limit={limit}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                raw_data = resp.json()
                if isinstance(raw_data, list) and len(raw_data) > 0:
                    candles = []
                    for row in raw_data:
                        if not isinstance(row, (list, tuple)) or len(row) < 6:
                            continue
                        try:
                            candles.append({
                                "openTime": int(row[0]),
                                "open": float(row[1]),
                                "high": float(row[2]),
                                "low": float(row[3]),
                                "close": float(row[4]),
                                "volume": float(row[5]),
                            })
                        except (TypeError, ValueError):
                            continue
                    if candles:
                        return candles
    except Exception as e:
        logger.debug(f"Binance Vision kline failed for {binance_sym}: {e}")

    # Fallback to Tokocrypto API
    try:
        from app.data.tokocrypto_client import tokocrypto_client
        symbols = await tokocrypto_client.fetch_symbols()
        sym_obj = None
        clean = symbol.upper().replace("/", "_")
        for s in symbols:
            if s.normalized_symbol == binance_sym or s.raw_symbol == clean:
                sym_obj = s
                break
        if sym_obj:
            return await tokocrypto_client.fetch_klines(sym_obj, interval=interval, limit=limit)
    except Exception as e:
        logger.warning(f"Tokocrypto kline fallback failed for {symbol}: {e}")

    return []


def calculate_ema(closes: list[float], period: int) -> list[Optional[float]]:
    """Calculate Exponential Moving Average."""
    if len(closes) < period:
        return [None] * len(closes)
    ema: list[Optional[float]] = [None] * (period - 1)
    # Start with SMA
    sma = sum(closes[:period]) / period
    ema.append(sma)
    multiplier = 2.0 / (period + 1)
    for price in closes[period:]:
        ema_val = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(ema_val)
    return ema


def calculate_rsi(closes: list[float], period: int = 14) -> Optional[float]:
    """Calculate latest 14-period RSI."""
    if len(closes) <= period:
        return None
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    if len(gains) < period:
        return None

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)


def generate_candlestick_chart(
    symbol_display: str,
    candles: list[dict],
    interval: str = "15m",
    position_data: Optional[dict] = None,
) -> Optional[io.BytesIO]:
    """Render dark-themed candlestick chart with indicators using Matplotlib.

    Returns io.BytesIO containing PNG image bytes.
    """
    if not candles or len(candles) < 5:
        return None

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle

    # Extract series
    n = len(candles)
    closes = [c["close"] for c in candles]
    opens = [c["open"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    # Convert timestamps (WIB is UTC+7)
    times = [
        datetime.fromtimestamp(c["openTime"] / 1000, tz=timezone.utc) + timedelta(hours=7)
        for c in candles
    ]

    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)

    # Styling setup
    bg_color = "#0c1017"
    card_bg = "#121824"
    grid_color = "#1e293b"
    text_color = "#94a3b8"
    green_color = "#10b981"
    red_color = "#ef4444"

    fig = plt.figure(figsize=(10, 6.2), facecolor=bg_color, dpi=120)
    gs = fig.add_gridspec(2, 1, height_ratios=[3.8, 1.2], hspace=0.08)

    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)

    for ax in (ax1, ax2):
        ax.set_facecolor(card_bg)
        ax.grid(True, linestyle="--", linewidth=0.5, color=grid_color, alpha=0.7)
        ax.tick_params(colors=text_color, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#1e293b")

    # Plot Candlesticks
    candle_width = 0.65
    indices = list(range(n))

    for i in range(n):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        is_up = c >= o
        color = green_color if is_up else red_color

        # Wick line
        ax1.plot([i, i], [l, h], color=color, linewidth=1.1, solid_capstyle="round", zorder=2)

        # Candle body
        body_bottom = min(o, c)
        body_height = max(abs(c - o), (h - l) * 0.015 if (h - l) > 0 else 0.000001)
        rect = Rectangle(
            (i - candle_width / 2.0, body_bottom),
            candle_width,
            body_height,
            facecolor=color,
            edgecolor=color,
            linewidth=0.8,
            zorder=3,
        )
        ax1.add_patch(rect)

        # Volume bar
        ax2.bar(i, volumes[i], width=candle_width, color=color, alpha=0.65, zorder=2)

    # Plot EMAs
    valid_e20_idx = [i for i, v in enumerate(ema20) if v is not None]
    if valid_e20_idx:
        ax1.plot(
            valid_e20_idx,
            [ema20[i] for i in valid_e20_idx],
            color="#f59e0b",
            linewidth=1.3,
            label="EMA 20",
            zorder=4,
        )

    valid_e50_idx = [i for i, v in enumerate(ema50) if v is not None]
    if valid_e50_idx:
        ax1.plot(
            valid_e50_idx,
            [ema50[i] for i in valid_e50_idx],
            color="#38bdf8",
            linewidth=1.3,
            label="EMA 50",
            zorder=4,
        )

    # Current Price Line
    last_price = closes[-1]
    first_price = opens[0]
    pct_change = ((last_price - first_price) / first_price) * 100.0
    ax1.axhline(last_price, color="#a855f7", linestyle=":", linewidth=1.1, alpha=0.9, zorder=4)

    # Open Position Markers (Entry, TP1, SL)
    if position_data:
        entry_p = position_data.get("entry_price")
        tp1_p = position_data.get("take_profit_1")
        sl_p = position_data.get("stop_loss")

        if entry_p:
            ax1.axhline(entry_p, color="#06b6d4", linestyle="--", linewidth=1.4, zorder=5, label=f"ENTRY ({entry_p:g})")
        if tp1_p:
            ax1.axhline(tp1_p, color="#22c55e", linestyle="--", linewidth=1.4, zorder=5, label=f"TP1 ({tp1_p:g})")
        if sl_p:
            ax1.axhline(sl_p, color="#f43f5e", linestyle="--", linewidth=1.4, zorder=5, label=f"SL ({sl_p:g})")

    # Title & Labels
    trend_arrow = "🟢 ▲" if pct_change >= 0 else "🔴 ▼"
    title_text = f"{symbol_display}  [{interval.upper()}]   {last_price:g} USDT   {trend_arrow} {pct_change:+.2f}%"
    ax1.set_title(title_text, color="#f8fafc", fontsize=13, fontweight="bold", pad=12, loc="left")

    ax1.legend(
        loc="upper left",
        facecolor=card_bg,
        edgecolor=grid_color,
        labelcolor=text_color,
        fontsize=8.5,
        framealpha=0.9,
    )

    # Format X-axis with WIB timestamps
    step = max(n // 7, 1)
    tick_indices = list(range(0, n, step))
    if tick_indices[-1] != n - 1:
        tick_indices.append(n - 1)
    tick_labels = [times[i].strftime("%H:%M") for i in tick_indices]

    ax2.set_xticks(tick_indices)
    ax2.set_xticklabels(tick_labels, rotation=0)
    ax2.set_xlabel("Waktu (WIB)", color=text_color, fontsize=8.5, labelpad=6)
    ax2.set_ylabel("Vol", color=text_color, fontsize=8.5)

    ax1.set_xlim(-1, n)
    ax2.set_xlim(-1, n)
    plt.setp(ax1.get_xticklabels(), visible=False)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf
