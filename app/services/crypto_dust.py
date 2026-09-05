"""Wallet dust detector & weekly reporter (READ-ONLY).

Dust = leftover spot balances too small to ever be sold individually, because
every Tokocrypto pair enforces a minimum order value (min_notional ≈ 5 USDT).
Leftovers accumulate from:
* taker fees deducted in the received asset (every trade, unavoidable),
* positions force-closed as SL_DUST before the 7-USDT sizing floor existed,
* stablecoins/pegged assets bought before the blacklist existed,
* partial fills recorded as full in the DB.

This module NEVER places orders. Cleanup is a manual one-click action via the
exchange's own "Convert Small Balance" feature; the report just tells the user
what is stuck and roughly what it is worth.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Fiat/quote balances never belong in the dust report: IDR is the user's own
# money and USDT is the bot's working cash.
FIAT_AND_QUOTE = {"IDR", "USDT"}


@dataclass
class AssetHolding:
    """One wallet asset with its price lookup result and computed value."""

    asset: str
    quantity: float
    price: Optional[float] = None
    is_pegged: bool = False

    @property
    def value(self) -> Optional[float]:
        if self.price is None:
            return None
        return self.quantity * self.price

    def line(self) -> str:
        # Avoid scientific notation for tiny balances (9.04e-06 reads badly
        # on Telegram; plain decimals with up to 8 dp stay legible).
        qty_str = f"{self.quantity:.8f}".rstrip("0").rstrip(".") or "0"
        if self.value is not None:
            return f"• {self.asset}: {qty_str} ≈ {self.value:.2f} USDT"
        return f"• {self.asset}: {qty_str} (harga tidak tersedia)"


@dataclass
class DustReport:
    """Result of one dust scan, split into buckets for the message builder."""

    active: list[AssetHolding] = field(default_factory=list)
    sellable: list[AssetHolding] = field(default_factory=list)
    dust: list[AssetHolding] = field(default_factory=list)
    prices_available: bool = True
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def dust_total(self) -> float:
        return sum(h.value or 0.0 for h in self.dust)

    @property
    def unknown_price_count(self) -> int:
        return sum(1 for h in self.dust if h.value is None)


def classify_assets(
    balances: dict[str, float],
    tickers: dict[str, dict],
    active_bases: set[str],
    quote_asset: str = "USDT",
    min_notional: float = 5.0,
    blacklist: set[str] = frozenset(),
) -> DustReport:
    """Pure classification of wallet balances into report buckets.

    Args:
        balances: ``{asset: free}`` from the trade client.
        tickers: ticker map keyed by no-underscore symbol (e.g. ``BTCUSDT``).
        active_bases: base assets backing open REAL positions.
        quote_asset: working cash of the bot (never reported).
        min_notional: exchange minimum order value (below = unsellable).
        blacklist: pegged base assets (stablecoins/gold/wrapped) from settings.

    Returns:
        A :class:`DustReport` with ``active``, ``sellable`` and ``dust`` lists.
    """
    report = DustReport()
    excluded = FIAT_AND_QUOTE | {quote_asset.upper()}

    for asset, qty in sorted(balances.items()):
        if not asset or qty <= 0:
            continue
        if asset.upper() in excluded:
            continue

        holding = AssetHolding(asset=asset, quantity=qty)
        ticker = tickers.get(f"{asset.upper()}{quote_asset.upper()}") or {}
        holding.price = ticker.get("lastPrice")
        if holding.price is None:
            report.prices_available = False
        if asset.upper() in blacklist:
            holding.is_pegged = True

        if asset.upper() in active_bases:
            report.active.append(holding)
        elif holding.value is not None and holding.value >= min_notional:
            report.sellable.append(holding)
        else:
            report.dust.append(holding)

    report.dust.sort(
        key=lambda h: (h.value is not None, h.value or 0.0), reverse=True
    )
    report.sellable.sort(key=lambda h: h.value or 0.0, reverse=True)
    return report


def parse_blacklist(raw: str) -> set[str]:
    """Parse the comma-separated ``crypto_real_symbol_blacklist`` setting."""
    return {s.strip().upper() for s in (raw or "").split(",") if s.strip()}


def format_dust_message(report: DustReport, max_items: int = 15) -> str:
    """Build the Telegram report text from a classification result."""
    text = "🔎 *DUST REPORT — Wallet Tokocrypto*\n\n"

    if report.active:
        text += "📍 *Posisi aktif (dipakai bot):*\n"
        for h in report.active:
            text += f"{h.line()}\n"
        text += "\n"

    if report.dust:
        total = report.dust_total
        text += f"🧹 *Dust: {len(report.dust)} aset"
        if report.prices_available:
            text += f" ≈ {total:.2f} USDT"
        text += "*\n"
        shown = report.dust[:max_items]
        for h in shown:
            line = h.line()
            if h.is_pegged and h.value is not None:
                line += " (pegged)"
            text += f"{line}\n"
        if len(report.dust) > len(shown):
            text += f"• … dan {len(report.dust) - len(shown)} aset lainnya\n"
        text += (
            "\n💤 Dust di bawah min_notional bursa (5 USDT) *tidak bisa dijual*"
            " lewat order biasa.\n"
            "👉 Pakai fitur *Convert Small Balance* di aplikasi Tokocrypto"
            " untuk mengubah semuanya jadi USDT.\n"
        )
    else:
        text += "🧹 *Dust: kosong — wallet bersih!*\n"

    if report.sellable:
        text += "\n💱 *Masih bisa dijual manual (≥ 5 USDT):*\n"
        for h in report.sellable:
            text += f"{h.line()}\n"

    text += "\n🔍 _Read-only report — bot tidak pernah menempatkan order._"
    return text


async def _get_open_real_bases() -> set[str]:
    """Base assets of open REAL positions (their coins are not dust)."""
    try:
        from sqlalchemy import select

        from app.db.session import async_session_factory
        from app.models.crypto import CryptoPaperPosition

        async with async_session_factory() as session:
            result = await session.execute(
                select(CryptoPaperPosition.base).where(
                    CryptoPaperPosition.status == "OPEN",
                    CryptoPaperPosition.mode == "REAL",
                )
            )
            return {row[0].upper() for row in result.all() if row[0]}
    except Exception as e:
        logger.warning(f"Cannot load open REAL positions: {e}")
        return set()


async def detect_dust() -> Optional[DustReport]:
    """Fetch wallet + prices and classify. None when the wallet is unreadable."""
    from app.data.tokocrypto_client import tokocrypto_client
    from app.data.tokocrypto_trade_client import TokoCryptoTradeClient

    client = TokoCryptoTradeClient()
    balances = await client.get_balances()
    if not balances:
        return None

    try:
        tickers = await tokocrypto_client.fetch_tickers()
    except Exception as e:
        logger.warning(f"Ticker fetch failed ({e}); reporting quantities only")
        tickers = {}

    active_bases = await _get_open_real_bases()
    return classify_assets(
        balances=balances,
        tickers=tickers,
        active_bases=active_bases,
        quote_asset=settings.crypto_real_quote_asset,
        min_notional=settings.crypto_real_min_order_quote,
        blacklist=parse_blacklist(settings.crypto_real_symbol_blacklist),
    )


async def _send_telegram(text: str) -> bool:
    chat_id = settings.telegram_chat_id or settings.telegram_admin_id
    if not settings.telegram_bot_token or not chat_id:
        logger.warning("Dust report: Telegram not configured, skipping send")
        return False
    try:
        from telegram import Bot

        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=chat_id, text=text, parse_mode="Markdown"
        )
        return True
    except Exception as e:
        logger.warning(f"Dust report Telegram send failed: {e}")
        return False


async def run_dust_report(notify: bool = True) -> Optional[str]:
    """Scan the wallet and (optionally) send the Telegram report.

    Returns the message text so the manual script can print it locally.
    """
    report = await detect_dust()
    if report is None:
        logger.warning("Dust report: wallet balances unavailable")
        return None
    message = format_dust_message(report)
    if notify:
        sent = await _send_telegram(message)
        if sent:
            logger.info("✅ Dust report sent to Telegram")
    return message
