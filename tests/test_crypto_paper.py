"""Tests for the crypto paper-trading engine."""

import pytest

from app.services.crypto_paper import PaperTrader, EXIT_TP1, EXIT_TP2, EXIT_SL
from tests.crypto_fixtures import make_candles_uptrend


def make_candidate(symbol="SUI_USDT", score=85.0, at_high=False, price=1.234, quote="USDT"):
    # NOTE: at_high defaults to False now — the shared entry gate rejects
    # candidates buying the top of a breakout spike (chasing).
    s1h = {
        "trend": "bullish",
        "rsi": 60.0,
        "price": price,
        "at_high": at_high,
        "relative_volume": 2.5,
        "ema20": price * 0.985,   # price ~1.5% above EMA20 → healthy pullback
        "macd_state": "bullish",
    }
    return {
        "symbol": symbol,
        "display": symbol.replace("_", "/"),
        "base": symbol.split("_")[0],
        "quote": quote,
        "price": price,
        "score": score,
        "tf_summaries": {"5m": {}, "15m": {}, "1h": s1h},
        "ticker": {"quoteVolume": "10000000", "priceChangePercent": "2.0"},
        "price_levels": {
            "entry": price,
            "take_profit_1": price * 1.05,
            "take_profit_2": price * 1.10,
            "stop_loss": price * 0.97,
        },
    }


def make_position(symbol="SUI_USDT", price=1.234, quote="USDT", status="OPEN"):
    class P:
        pass
    p = P()
    p.id = "pos-1"
    p.symbol = symbol
    p.base = "SUI"
    p.quote = quote
    p.display = "SUI/USDT"
    p.status = status
    p.entry_price = price
    p.quantity = 10.0
    p.invested = price * 10.0
    p.take_profit_1 = price * 1.05
    p.take_profit_2 = price * 1.10
    p.stop_loss = price * 0.97
    p.entry_score = 85.0
    p.highest_price = price
    p.atr_value = price * 0.02
    return p


@pytest.fixture
def trader(monkeypatch):
    t = PaperTrader()
    return t


class TestEntryGate:
    def test_accepts_high_score_breakout(self, trader, monkeypatch):
        # Legacy breakout mode: uptrend/pullback gates off, breakout required.
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_require_breakout", True)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_require_uptrend", False)
        assert trader._passes_entry_gate(make_candidate(score=85, at_high=True))

    def test_rejects_low_score(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        assert not trader._passes_entry_gate(make_candidate(score=70, at_high=True))

    def test_rejects_no_breakout_when_required(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_require_breakout", True)
        assert not trader._passes_entry_gate(make_candidate(score=90, at_high=False))

    def test_accepts_no_breakout_when_not_required(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_require_breakout", False)
        assert trader._passes_entry_gate(make_candidate(score=85, at_high=False))

    def test_rejects_bearish_trend_when_uptrend_required(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_require_uptrend", True)
        cand = make_candidate(score=90, at_high=False)
        cand["tf_summaries"]["1h"]["trend"] = "bearish"
        assert not trader._passes_entry_gate(cand)

    def test_rejects_neutral_macd_when_uptrend_required(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_require_uptrend", True)
        cand = make_candidate(score=90, at_high=False)
        cand["tf_summaries"]["1h"]["macd_state"] = "neutral"
        assert not trader._passes_entry_gate(cand)

    def test_rejects_extended_price_above_ema20(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_pullback_max_pct", 3.0)
        cand = make_candidate(score=90, at_high=False)
        cand["tf_summaries"]["1h"]["ema20"] = cand["price"] * 0.9  # 11% above EMA20
        assert not trader._passes_entry_gate(cand)

    def test_rejects_at_high_when_pullback_strategy(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_pullback_max_pct", 3.0)
        cand = make_candidate(score=90, at_high=True)
        assert not trader._passes_entry_gate(cand)

    def test_accepts_healthy_pullback_in_uptrend(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_require_uptrend", True)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_pullback_max_pct", 3.0)
        # price 1.5% above EMA20, not at high → healthy pullback
        cand = make_candidate(score=88, at_high=False)
        assert trader._passes_entry_gate(cand)

    def test_ai_filter_rejects_neutral_or_avoid(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_pullback_max_pct", 3.0)
        monkeypatch.setattr(get_settings(), "crypto_paper_ai_filter_enabled", True)
        for verdict in ("NEUTRAL", "AVOID"):
            cand = make_candidate(score=90, at_high=False)
            cand["ai_verdict"] = {"verdict": verdict}
            assert not trader._passes_entry_gate(cand), f"should reject {verdict}"

    def test_ai_filter_accepts_strong_watch_verdicts(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_pullback_max_pct", 3.0)
        monkeypatch.setattr(get_settings(), "crypto_paper_ai_filter_enabled", True)
        # The shared REAL entry gate only accepts STRONG_WATCH (see comment at
        # the test below) — WATCH is rejected by passes_entry_gate itself.
        for verdict in ("STRONG_WATCH",):
            cand = make_candidate(score=90, at_high=False)
            cand["ai_verdict"] = {"verdict": verdict}
            assert trader._passes_entry_gate(cand), f"should accept {verdict}"

    def test_ai_verdict_avoid_rejected_even_if_paper_filter_disabled(self, trader, monkeypatch):
        # Paper now shares the REAL entry gate: a non-STRONG_WATCH verdict is
        # always rejected there — the old paper-side ai_filter flag is unused.
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_pullback_max_pct", 3.0)
        monkeypatch.setattr(get_settings(), "crypto_paper_ai_filter_enabled", False)
        cand = make_candidate(score=90, at_high=False)
        cand["ai_verdict"] = {"verdict": "AVOID"}
        assert not trader._passes_entry_gate(cand)

    def test_ai_filter_missing_verdict_is_not_blocking(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_entry_score", 80)
        monkeypatch.setattr(get_settings(), "crypto_real_entry_pullback_max_pct", 3.0)
        monkeypatch.setattr(get_settings(), "crypto_paper_ai_filter_enabled", True)
        cand = make_candidate(score=90, at_high=False)  # no ai_verdict key
        assert trader._passes_entry_gate(cand)


class TestExitDecision:
    def test_no_exit_when_inside_range(self, trader):
        pos = make_position()
        assert trader._decide_exit(pos, 1.20) is None  # between SL and TP1

    def test_tp1_when_price_reaches_tp1(self, trader):
        pos = make_position()
        assert trader._decide_exit(pos, 1.234 * 1.05) == EXIT_TP1

    def test_tp2_preferred_over_tp1(self, trader):
        pos = make_position()
        assert trader._decide_exit(pos, 1.234 * 1.10) == EXIT_TP2

    def test_sl_when_price_drops(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_sl_exit_tolerance_pct", 0.0)
        pos = make_position()
        assert trader._decide_exit(pos, 1.234 * 0.97) == EXIT_SL

    def test_sl_wick_guard_holds_within_tolerance(self, trader, monkeypatch):
        """A dip just past SL (within the wick tolerance) must NOT exit."""
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_real_sl_exit_tolerance_pct", 0.5)
        pos = make_position()
        # price exactly at SL — a single snapshot wick → hold the position.
        assert trader._decide_exit(pos, 1.234 * 0.97) is None
        # price genuinely below SL by more than 0.5% → exit.
        assert trader._decide_exit(pos, 1.234 * 0.965) == EXIT_SL

    def test_sl_beats_tp_when_both_odd(self, trader):
        pos = make_position()
        # Hypothetically price below SL and above TP2 — SL must win.
        pos.stop_loss = 10.0
        pos.take_profit_2 = 1.0
        assert trader._decide_exit(pos, 5.0) == EXIT_SL


class TestClosePosition:
    @pytest.mark.asyncio
    async def test_close_via_each_action_no_keyerror(self, trader, monkeypatch):
        """Closing via TP1/TP2/SL must not raise KeyError on the side mapping."""
        from app.services.crypto_paper import (
            EXIT_TP1, EXIT_TP2, EXIT_SL, SIDE_SELL_TP1, SIDE_SELL_TP2, SIDE_SELL_SL,
        )
        from app.models.crypto import CryptoPaperPosition, CryptoPaperTrade

        monkeypatch.setattr("app.services.crypto_paper.settings.crypto_paper_notify", False)

        class Account:
            def __init__(self, quote="USDT"):
                self.quote_asset = quote
                self.cash_balance = 10000.0
                self.realized_pnl = 0.0
                self.total_trades = 0
                self.winning_trades = 0

        class FakeSession:
            def __init__(self):
                self.added = []
            def add(self, obj):
                self.added.append(obj)
            async def flush(self):
                pass

        for action, expected_side in (
            (EXIT_TP1, SIDE_SELL_TP1),
            (EXIT_TP2, SIDE_SELL_TP2),
            (EXIT_SL, SIDE_SELL_SL),
        ):
            session = FakeSession()
            pos = make_position()
            pos.id = 1
            session.add(pos)
            await session.flush()

            account = Account()
            await trader._close_position(session, pos, account, action, 1.20)

            trade = next(
                (o for o in session.added if isinstance(o, CryptoPaperTrade)),
                None,
            )
            assert trade is not None, f"no trade recorded for {action}"
            assert trade.side == expected_side
            assert pos.status == "CLOSED"
            assert pos.exit_reason == action


class TestPriceLookup:
    def test_normalizes_symbol(self, trader):
        assert trader._current_price({"SUIUSDT": {"lastPrice": 1.5}}, "SUI_USDT") == 1.5

    def test_missing_ticker_returns_none(self, trader):
        assert trader._current_price({}, "SUI_USDT") is None


@pytest.mark.asyncio
async def test_run_cycle_disabled(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_paper_trading_enabled", False)

    class EmptyResult:
        def scalars(self): return self
        def all(self): return []

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def commit(self): pass
        async def execute(self, *a, **k): return EmptyResult()

    def fake_factory():
        return FakeSession()

    monkeypatch.setattr("app.db.session.async_session_factory", fake_factory)

    t = PaperTrader()
    # No candidates → no entries, and no DB access needed for exits.
    result = await t.run_cycle([], {})
    assert result["status"] == "ok"
    assert result["positions_opened"] == 0


@pytest.mark.asyncio
async def test_open_position_debets_account(monkeypatch):
    """Verify _open_position deducts allocation and records a BUY trade."""
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "crypto_paper_allocation_percent", 10.0)
    monkeypatch.setattr(get_settings(), "crypto_paper_notify", False)

    class Account:
        def __init__(self):
            self.quote_asset = "USDT"
            self.cash_balance = 10000.0

    class FakeSession:
        def __init__(self):
            self.added = []
        def add(self, obj): self.added.append(obj)
        async def flush(self): pass

    session = FakeSession()
    trader = PaperTrader()
    cand = make_candidate()
    account = Account()
    await trader._open_position(session, account, cand, cand["price"])

    from app.models.crypto import CryptoPaperPosition, CryptoPaperTrade
    pos = next(o for o in session.added if isinstance(o, CryptoPaperPosition))
    trade = next(o for o in session.added if isinstance(o, CryptoPaperTrade))

    assert account.cash_balance == 9000.0  # 10% of 10000 spent
    assert pos.status == "OPEN"
    assert pos.entry_price == cand["price"]
    assert pos.invested == pytest.approx(1000.0)
    assert trade.side == "BUY"
    assert trade.quote_amount == pytest.approx(1000.0)


class TestTelegramAccountSummary:
    def test_account_summary_text_includes_balance_and_pnl(self, trader):
        class Account:
            quote_asset = "USDT"
            cash_balance = 708333.69
            realized_pnl = -1694.21
            total_trades = 7
            winning_trades = 3

        text = trader._account_summary_text(Account())
        assert "Ringkasan Akun" in text
        assert "708,333.69" in text
        assert "-1,694.21" in text
        assert "7" in text and "3" in text

    def test_account_summary_none_returns_empty(self, trader):
        assert trader._account_summary_text(None) == ""

    @pytest.mark.asyncio
    async def test_notify_open_includes_account_summary(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_paper_notify", True)
        sent = {}

        async def fake_send(text):
            sent["text"] = text
        monkeypatch.setattr(trader, "_send_telegram", fake_send)

        class Account:
            quote_asset = "USDT"
            cash_balance = 9000.0
            realized_pnl = -10.0
            total_trades = 2
            winning_trades = 1

        pos = make_position()
        await trader._notify_open(pos, Account())
        assert "PAPER BUY" in sent["text"]
        assert "Ringkasan Akun" in sent["text"]
        assert "Saldo" in sent["text"]

    @pytest.mark.asyncio
    async def test_notify_close_profit_shows_untung(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_paper_notify", True)
        sent = {}

        async def fake_send(text):
            sent["text"] = text
        monkeypatch.setattr(trader, "_send_telegram", fake_send)

        class Account:
            quote_asset = "USDT"
            cash_balance = 9000.0
            realized_pnl = 500.0
            total_trades = 3
            winning_trades = 2

        pos = make_position()
        await trader._notify_close(pos, "TP1", 1.20, 50.0, Account())
        assert "UNTUNG" in sent["text"]
        assert "Ringkasan Akun" in sent["text"]
        assert "+500.00" in sent["text"]

    @pytest.mark.asyncio
    async def test_notify_close_loss_shows_rugi(self, trader, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_paper_notify", True)
        sent = {}

        async def fake_send(text):
            sent["text"] = text
        monkeypatch.setattr(trader, "_send_telegram", fake_send)

        class Account:
            quote_asset = "USDT"
            cash_balance = 8000.0
            realized_pnl = -300.0
            total_trades = 4
            winning_trades = 1

        pos = make_position()
        await trader._notify_close(pos, "SL", 0.80, -120.0, Account())
        assert "RUGI" in sent["text"]
        assert "Ringkasan Akun" in sent["text"]
        assert "-300.00" in sent["text"]


class TestSlCooldown:
    @pytest.mark.asyncio
    async def test_symbol_in_sl_cooldown_is_skipped(self, monkeypatch):
        """A symbol that hit SL within the cooldown window is not re-entered."""
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_paper_sl_cooldown_minutes", 120)
        monkeypatch.setattr(get_settings(), "crypto_paper_notify", False)
        monkeypatch.setattr(get_settings(), "crypto_paper_max_positions", 5)

        class SLSymbol:
            symbol = "DOLO_USDT"

        class EmptyResult:
            def __init__(self):
                self.calls = 0
            def scalars(self): return self
            def all(self):
                self.calls += 1
                # 1st query = open symbols ([]), 2nd = SL cooldown ([DOLO_USDT])
                return [] if self.calls == 1 else [SLSymbol]
            def scalar(self): return 0
            def scalar_one_or_none(self): return None

        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def commit(self): pass
            async def execute(self, stmt, *a, **k):
                return EmptyResult()

        def fake_factory():
            return FakeSession()

        monkeypatch.setattr("app.db.session.async_session_factory", fake_factory)
        # Prevent actual _open_position from running (would need DB); make it fail loudly.
        async def boom(*a, **k):
            raise AssertionError("DOLO_USDT must not be opened during cooldown")
        monkeypatch.setattr(PaperTrader, "_open_position", boom)

        t = PaperTrader()
        cand = make_candidate(symbol="DOLO_USDT", at_high=False)
        result = await t.run_cycle([cand], {})
        assert result["positions_opened"] == 0

    @pytest.mark.asyncio
    async def test_symbol_without_recent_sl_is_opened(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), "crypto_paper_sl_cooldown_minutes", 120)
        monkeypatch.setattr(get_settings(), "crypto_paper_notify", False)
        monkeypatch.setattr(get_settings(), "crypto_paper_ai_filter_enabled", False)

        class EmptyResult:
            def scalars(self): return self
            def all(self): return []
            def scalar(self): return 0
            def scalar_one_or_none(self): return None

        class FakeSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def commit(self): pass
            async def flush(self): pass
            def add(self, obj): pass
            async def execute(self, stmt, *a, **k): return EmptyResult()

        def fake_factory():
            return FakeSession()

        monkeypatch.setattr("app.db.session.async_session_factory", fake_factory)

        opened = {}

        async def fake_open(self, session, account, cand, price):
            opened["symbol"] = cand.get("symbol")
        monkeypatch.setattr(PaperTrader, "_open_position", fake_open)

        t = PaperTrader()
        cand = make_candidate(symbol="SUI_USDT", at_high=False)
        result = await t.run_cycle([cand], {})
        assert result["positions_opened"] == 1
        assert opened["symbol"] == "SUI_USDT"