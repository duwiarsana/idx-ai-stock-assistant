"""Tests for the dust detection service (pure logic — no API calls)."""

import pytest

from app.services.crypto_dust import (
    AssetHolding,
    DustReport,
    classify_assets,
    format_dust_message,
    parse_blacklist,
)

TICKERS = {
    "XPLUSDT": {"lastPrice": 0.09544},
    "ETCUSDT": {"lastPrice": 7.70},
    "WLFIUSDT": {"lastPrice": 0.06},
    "USD1USDT": {"lastPrice": 1.0},
    "BTCUSDT": {"lastPrice": 100000.0},
    "COTIUSDT": {"lastPrice": 0.0127},
}

BALANCES = {
    "USDT": 14.71,       # bot cash — excluded
    "IDR": 79506.37,     # user's fiat — excluded
    "XPL": 73.2,         # open position — active
    "ETC": 0.91,         # open position — active
    "WLFI": 46.17,       # ~2.77 USDT — dust
    "USD1": 5.95,        # ~5.95 USDT — sellable (pegged)
    "BTC": 0.00000904,   # ~0.9 USDT — dust
    "COTI": 0.79,        # ~0.01 USDT — dust
}


def classify(balances=None, tickers=None, active=None):
    return classify_assets(
        balances=balances if balances is not None else BALANCES,
        tickers=tickers if tickers is not None else TICKERS,
        active_bases=active if active is not None else {"XPL", "ETC"},
        quote_asset="USDT",
        min_notional=5.0,
        blacklist=parse_blacklist("USD1,PAXG,XAUT"),
    )


def test_quote_and_fiat_excluded():
    report = classify()
    names = [h.asset for h in report.active + report.sellable + report.dust]
    assert "USDT" not in names
    assert "IDR" not in names


def test_open_positions_classified_active():
    report = classify()
    active = {h.asset for h in report.active}
    assert active == {"XPL", "ETC"}


def test_dust_below_min_notional():
    report = classify()
    dust = {h.asset for h in report.dust}
    assert dust == {"WLFI", "BTC", "COTI"}


def test_sellable_above_min_notional():
    report = classify()
    sellable = {h.asset for h in report.sellable}
    assert sellable == {"USD1"}


def test_dust_total_ignores_unknown_prices():
    report = classify()
    assert report.dust_total == pytest.approx(2.77 + 0.9 + 0.79 * 0.0127, abs=0.01)


def test_missing_price_marks_unavailable():
    report = classify(tickers={})
    assert report.prices_available is False
    assert all(h.value is None for h in report.dust)


def test_missing_price_goes_to_dust():
    """Assets without a price cannot be proven sellable — treat as dust."""
    report = classify(tickers={})
    names = {h.asset for h in report.dust}
    assert "WLFI" in names and "USD1" in names


def test_pegged_flag_from_blacklist():
    report = classify()
    usd1 = next(h for h in report.sellable if h.asset == "USD1")
    assert usd1.is_pegged is True


def test_dust_sorted_by_value_desc():
    report = classify()
    values = [h.value for h in report.dust]
    assert values == sorted(values, reverse=True)


def test_empty_wallet_returns_empty_report():
    report = classify(balances={})
    assert not report.active
    assert not report.dust
    assert not report.sellable


def test_parse_blacklist_strips_and_uppercases():
    assert parse_blacklist(" usd1 , PaxG , , WBETH ") == {"USD1", "PAXG", "WBETH"}


def test_message_contains_totals_and_hint():
    report = classify()
    msg = format_dust_message(report)
    assert "DUST REPORT" in msg
    assert "WLFI" in msg
    assert "Convert Small Balance" in msg


def test_message_dust_list_capped():
    report = DustReport()
    for i in range(25):
        report.dust.append(
            AssetHolding(asset=f"C{i}", quantity=1.0, price=0.01)
        )
    msg = format_dust_message(report)
    assert "dan 10 aset lainnya" in msg
