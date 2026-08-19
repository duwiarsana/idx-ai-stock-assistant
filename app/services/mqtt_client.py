"""MQTT publisher for paper-trading events (ESP32 sound alerts).

Publishes JSON messages to a Mosquitto broker:
* ``<prefix>/buy``       — a paper position was opened
* ``<prefix>/profit``    — a position was closed at TP1 / TP2 (profit)
* ``<prefix>/loss``      — a position was closed at SL (cut loss)
* ``<prefix>/heartbeat`` — periodic "bot alive" beacon (for ESP32 watchdog/LED)

Publishing is best-effort and never fatal: if the broker is unreachable or MQTT
is disabled, every call degrades to a no-op log line.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MqttPublisher:
    """Async MQTT publisher with a background heartbeat task."""

    def __init__(self):
        self._client = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._publish_lock = asyncio.Lock()
        self.state = {"connected": False, "published": 0, "last_error": None}

    # ── Lifecycle ────────────────────────────────────────────────────

    def enabled(self) -> bool:
        return bool(settings.mqtt_enabled and settings.mqtt_host)

    async def start(self) -> None:
        """Start the heartbeat task (idempotent)."""
        if not self.enabled():
            return
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await self.publish("heartbeat", {"status": "alive"})
            except Exception as e:
                logger.debug(f"MQTT heartbeat error: {e}")
            await asyncio.sleep(max(10, settings.mqtt_heartbeat_seconds))

    # ── Client management ────────────────────────────────────────────

    def _new_client(self):
        import aiomqtt

        return aiomqtt.Client(
            hostname=settings.mqtt_host,
            port=settings.mqtt_port,
            username=settings.mqtt_username or None,
            password=settings.mqtt_password or None,
            identifier="idx-ai-bot",
            keepalive=30,
        )

    # ── Publish ──────────────────────────────────────────────────────

    async def publish(self, event: str, payload: dict) -> bool:
        """Publish ``payload`` to ``<prefix>/<event>``. Returns success."""
        if not self.enabled():
            return False

        topic = f"{settings.mqtt_topic_prefix.rstrip('/')}/{event}"
        message = json.dumps(payload, default=str)

        async with self._publish_lock:
            try:
                client = self._new_client()
                async with client as c:
                    await asyncio.wait_for(
                        c.publish(topic, message, qos=1),
                        timeout=settings.mqtt_timeout,
                    )
                self.state["connected"] = True
                self.state["published"] += 1
                logger.info(f"📡 MQTT published {topic}: {message[:120]}")
                return True
            except Exception as e:
                self.state["connected"] = False
                self.state["last_error"] = str(e)
                logger.warning(f"MQTT publish failed ({topic}): {e}")
                return False

    # ── Convenience event builders ───────────────────────────────────

    async def publish_buy(self, pos, account=None) -> bool:
        payload = self._pos_payload(pos, event="BUY")
        payload.update(self._account_payload(account))
        return await self.publish("buy", payload)

    async def publish_profit(self, pos, exit_price: float, pnl: float, account=None) -> bool:
        payload = self._pos_payload(pos, event="PROFIT")
        payload.update({
            "exit_price": exit_price,
            "exit_reason": pos.exit_reason or "TP",
            "pnl": round(pnl, 6),
            "pnl_percent": self._pnl_percent(pos, pnl),
        })
        payload.update(self._account_payload(account))
        return await self.publish("profit", payload)

    async def publish_loss(self, pos, exit_price: float, pnl: float, account=None) -> bool:
        payload = self._pos_payload(pos, event="LOSS")
        payload.update({
            "exit_price": exit_price,
            "exit_reason": pos.exit_reason or "SL",
            "pnl": round(pnl, 6),
            "pnl_percent": self._pnl_percent(pos, pnl),
        })
        payload.update(self._account_payload(account))
        return await self.publish("loss", payload)

    @staticmethod
    def _account_payload(account) -> dict:
        """Account summary so the ESP32/display can show current balance & PnL."""
        if account is None:
            return {}
        return {
            "balance": round(getattr(account, "cash_balance", 0.0) or 0.0, 2),
            "realized_pnl": round(getattr(account, "realized_pnl", 0.0) or 0.0, 2),
            "total_trades": getattr(account, "total_trades", 0) or 0,
            "winning_trades": getattr(account, "winning_trades", 0) or 0,
        }

    @staticmethod
    def _pos_payload(pos, event: str) -> dict:
        return {
            "event": event,
            "symbol": pos.symbol,
            "display": pos.display or pos.symbol,
            "base": pos.base,
            "quote": pos.quote,
            "entry_price": pos.entry_price,
            "quantity": pos.quantity,
            "invested": pos.invested,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _pnl_percent(pos, pnl: float) -> Optional[float]:
        invested = pos.invested or 0.0
        if invested <= 0:
            return None
        return round((pnl / invested) * 100, 2)


# Singleton
mqtt_publisher = MqttPublisher()