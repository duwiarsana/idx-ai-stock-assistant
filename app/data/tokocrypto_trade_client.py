"""Tokocrypto private (SIGNED) trading client — REAL MONEY.

Only touch this module through :class:`CryptoRealTrader`. It talks to the
private API with HMAC-SHA256 signatures and is deliberately thin: it never
decides anything, it only executes orders and reads balances.

Security rules:
* API secret lives ONLY in environment config (never committed, never logged).
* The key MUST be created with TRADE-only permissions (disable Withdraw).
* Every call uses ``recvWindow <= 5000`` and a fresh millisecond timestamp.
* No withdrawal endpoint is ever exposed here.

Endpoints used:
* POST /open/v1/orders            — new order (SIGNED, HMAC SHA256)
* GET  /open/v1/account/spot      — account balances (SIGNED)
* GET  /open/v1/orders/detail     — order status (SIGNED)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

TRADE_BASE = "https://www.tokocrypto.com"

# side: 0 = BUY, 1 = SELL
SIDE_BUY = 0
SIDE_SELL = 1
# type: 1 = LIMIT, 2 = MARKET
ORDER_MARKET = 2

# Order status codes (see docs)
STATUS_NEW = 0
STATUS_PARTIALLY_FILLED = 1
STATUS_FILLED = 2
STATUS_CANCELED = 3


class TokoTradeError(Exception):
    """Raised when the private API rejects a signed request."""


class TokoCryptoTradeClient:
    """Minimal HMAC-SHA256 signed client for spot trading."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        timeout: float = 15.0,
    ):
        self.api_key = api_key or settings.crypto_real_api_key
        self.api_secret = api_secret or settings.crypto_real_api_secret
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _assert_configured(self) -> None:
        if not self.api_key or not self.api_secret:
            raise TokoTradeError(
                "Real-trading API key/secret not configured "
                "(CRYPTO_REAL_API_KEY / CRYPTO_REAL_API_SECRET)."
            )

    def _sign(self, params: dict) -> dict:
        # IMPORTANT: Tokocrypto signs the params in INSERTION ORDER — never
        # alphabetically sort them. `totalParams` = query string + request body,
        # and the sent request must carry the params in the same order as the
        # signed string (httpx preserves dict insertion order for both GET query
        # strings and POST form bodies).
        query = urlencode(params)
        sig = hmac.new(
            self.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = sig
        return params

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _signed_params(self, **extra) -> dict:
        params = {
            "timestamp": int(time.time() * 1000),
            "recvWindow": 5000,
        }
        params.update({k: v for k, v in extra.items() if v is not None})
        return self._sign(params)

    async def _request(self, method: str, endpoint: str, params: dict) -> dict:
        self._assert_configured()
        client = await self._get_client()
        url = f"{TRADE_BASE}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key}
        try:
            if method.upper() == "GET":
                resp = await client.get(url, params=params, headers=headers)
            else:
                resp = await client.post(url, data=params, headers=headers)
        except httpx.HTTPError as e:
            raise TokoTradeError(f"Network error on {endpoint}: {e}") from e

        try:
            payload = resp.json()
        except ValueError as e:
            raise TokoTradeError(f"Bad JSON from {endpoint}: {resp.text[:200]}") from e

        # Tokocrypto wraps responses in {code, msg, data, ...}.
        if isinstance(payload, dict) and "code" in payload and payload.get("code") not in (0, None):
            msg = payload.get("msg") or payload.get("message") or str(payload.get("code"))
            raise TokoTradeError(f"API error {payload.get('code')} on {endpoint}: {msg}")
        return payload

    # ── Account ──────────────────────────────────────────────────────

    async def get_balance(self, asset: str) -> Optional[float]:
        """Return the free balance of ``asset`` (e.g. 'USDT'), or None."""
        payload = await self._request(
            "GET",
            "/open/v1/account/spot/asset",
            self._signed_params(asset=asset.upper()),
        )
        data = payload.get("data") or {}
        free = data.get("free")
        return float(free) if free is not None else None

    async def get_balances(self) -> dict[str, float]:
        """Return {asset: free} for every non-zero balance."""
        payload = await self._request("GET", "/open/v1/account/spot", self._signed_params())
        data = payload.get("data") or {}
        out: dict[str, float] = {}
        for row in data.get("accountAssets", []) or []:
            try:
                free = float(row.get("free") or 0)
            except (TypeError, ValueError):
                free = 0.0
            if free > 0:
                out[str(row.get("asset", ""))] = free
        return out

    # ── Symbol rules (LOT_SIZE / NOTIONAL) ───────────────────────────

    async def get_symbol_rules(self, symbol: str) -> dict:
        """Return trading rules for a symbol: lot step, min notional, decimals.

        Uses the public endpoint (no auth). Falls back to sane defaults so a
        failure never blocks order placement entirely.
        """
        symbol = symbol.replace("_", "_")
        client = await self._get_client()
        try:
            resp = await client.get(
                f"{TRADE_BASE}/open/v1/common/symbols",
                params={"symbol": symbol},
            )
            payload = resp.json()
            rows = (payload.get("data") or {}).get("list") or []
            row = next((r for r in rows if r.get("symbol") == symbol), None)
            if not row:
                return self._default_rules(symbol)
            filters = row.get("filters") or []
            lot = next((f for f in filters if f.get("filterType") == "LOT_SIZE"), {})
            noti = next((f for f in filters if f.get("filterType") == "NOTIONAL"), {})
            return {
                "step_size": float(lot.get("stepSize") or 0),
                "min_qty": float(lot.get("minQty") or 0),
                "min_notional": float(noti.get("minNotional") or 0),
            }
        except Exception:
            return self._default_rules(symbol)

    @staticmethod
    def _default_rules(symbol: str) -> dict:
        # Safe defaults: 8 decimals, step 1e-8, min notional 5 (USDT pairs).
        return {"step_size": 1e-8, "min_qty": 1e-8, "min_notional": 5.0}

    @staticmethod
    def round_up_to_step(value: float, step: float) -> float:
        """Round ``value`` UP to the nearest multiple of ``step``."""
        if not step or step <= 0:
            return value
        import math
        return math.ceil(value / step - 1e-12) * step

    @staticmethod
    def round_down_to_step(value: float, step: float) -> float:
        """Round ``value`` DOWN to the nearest multiple of ``step``."""
        if not step or step <= 0:
            return value
        import math
        return math.floor(value / step + 1e-12) * step

    @staticmethod
    def fmt_qty(value: float) -> str:
        """Format a quantity as a plain decimal string (no scientific notation)."""
        return f"{value:.10f}".rstrip("0").rstrip(".") or "0"

    # ── Orders ───────────────────────────────────────────────────────

    async def market_buy(self, symbol: str, quantity: float) -> dict:
        """Buy ``quantity`` of the base asset at market price.

        Uses ``quantity`` (not ``quoteOrderQty``) because for very small
        accounts a ``quoteOrderQty`` spend can round DOWN to a position whose
        notional falls below the exchange ``NOTIONAL`` filter — which would then
        be impossible to sell. The caller computes ``quantity`` from the balance
        and rounds it UP to the LOT_SIZE step so the resulting position is
        always sellable (notional >= min order value).
        """
        return await self._request(
            "POST",
            "/open/v1/orders",
            self._signed_params(
                symbol=symbol.replace("_", "_"),
                side=SIDE_BUY,
                type=ORDER_MARKET,
                quantity=self.fmt_qty(quantity),
            ),
        )

    async def market_sell(self, symbol: str, quantity: float) -> dict:
        """Sell ``quantity`` of the base asset at market price.

        ``quantity`` must be a multiple of the symbol LOT_SIZE step and its
        notional must be >= NOTIONAL.minNotional, or the exchange rejects it.
        """
        return await self._request(
            "POST",
            "/open/v1/orders",
            self._signed_params(
                symbol=symbol.replace("_", "_"),
                side=SIDE_SELL,
                type=ORDER_MARKET,
                quantity=self.fmt_qty(quantity),
            ),
        )

    async def get_order(self, symbol: str, order_id: Any) -> dict:
        payload = await self._request(
            "GET",
            "/open/v1/orders/detail",
            self._signed_params(symbol=symbol.replace("_", "_"), orderId=order_id),
        )
        return payload.get("data") or {}

    @staticmethod
    def parse_fill(payload: dict) -> dict:
        """Extract a normalised fill summary from an order response."""
        data = payload.get("data") or payload
        try:
            price = float(data.get("executedPrice") or data.get("price") or 0)
            qty = float(data.get("executedQty") or data.get("origQty") or 0)
        except (TypeError, ValueError):
            price, qty = 0.0, 0.0
        return {
            "order_id": data.get("orderId"),
            "status": data.get("status"),
            "price": price,
            "quantity": qty,
            "quote_amount": float(data.get("executedQuoteQty") or data.get("origQuoteQty") or 0)
            if data.get("executedQuoteQty") is not None
            else float(data.get("origQuoteQty") or 0),
            "symbol": data.get("symbol"),
        }


# Singleton — reads credentials from settings lazily on first use.
trade_client = TokoCryptoTradeClient()