"""Requirement 22: prove market data is real and the maths is correct.

The central claim under test is negative: **the system must never invent a
number**. So most of these tests assert that a missing input produces a
rejection, not a default.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from tests.conftest import make_bars
from src.market.indicators import (
    atr,
    compute_indicators,
    derive_levels,
    describe_technicals,
    rsi,
    sma,
    swing_support_resistance,
    trend_bias,
    true_range,
)
from src.market.quotes import normalise_ticker
from src.market.session import IST, market_status, previous_trading_day


# ---------------------------------------------------------------------------
# Indicator maths
# ---------------------------------------------------------------------------

def test_sma_matches_hand_calculation():
    values = [10, 20, 30, 40, 50]
    assert sma(values, 5) == pytest.approx(30.0)
    assert sma(values, 2) == pytest.approx(45.0)


def test_sma_returns_none_when_history_is_short():
    assert sma([1, 2, 3], 20) is None, "a 20-period average over 3 points is not an average"


def test_rsi_is_100_for_a_pure_uptrend():
    closes = [100 + i for i in range(40)]
    assert rsi(closes, 14) == pytest.approx(100.0)


def test_rsi_is_0_for_a_pure_downtrend():
    closes = [100 - i for i in range(40)]
    assert rsi(closes, 14) == pytest.approx(0.0)


def test_rsi_matches_independent_wilder_recomputation():
    """Cross-check against a from-scratch implementation of Wilder's method."""
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
              45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
              46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57,
              43.42, 42.66, 43.13]
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    avg_gain, avg_loss = sum(gains[:14]) / 14, sum(losses[:14]) / 14
    for gain, loss in zip(gains[14:], losses[14:]):
        avg_gain = (avg_gain * 13 + gain) / 14
        avg_loss = (avg_loss * 13 + loss) / 14
    expected = 100 - (100 / (1 + avg_gain / avg_loss))
    assert rsi(closes, 14) == pytest.approx(expected, abs=1e-9)


def test_rsi_returns_none_without_enough_history():
    assert rsi([1, 2, 3, 4], 14) is None


def test_true_range_uses_the_widest_of_three():
    assert true_range(high=110, low=100, prev_close=105) == pytest.approx(10.0)
    # Gap up: prev close far below the low.
    assert true_range(high=120, low=118, prev_close=100) == pytest.approx(20.0)


def test_atr_is_positive_and_scales_with_volatility():
    calm = make_bars(60, base=100, step=0.1)
    wild = [{"timestamp": datetime(2026, 1, 1) + timedelta(days=i),
             "open": 100, "high": 100 + (5 if i % 2 else 0), "low": 100 - (5 if i % 2 else 0),
             "close": 100, "volume": 1.0} for i in range(60)]
    calm_atr = atr([b["high"] for b in calm], [b["low"] for b in calm], [b["close"] for b in calm])
    wild_atr = atr([b["high"] for b in wild], [b["low"] for b in wild], [b["close"] for b in wild])
    assert calm_atr > 0 and wild_atr > calm_atr


def test_support_and_resistance_are_window_extremes():
    lows = [10, 9, 11, 8, 12]
    highs = [15, 16, 14, 17, 13]
    support, resistance = swing_support_resistance(lows, highs, lookback=5)
    assert support == 8 and resistance == 17


# ---------------------------------------------------------------------------
# Indicator assembly
# ---------------------------------------------------------------------------

def test_indicators_use_the_real_series():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=1.0))
    assert ind.bars == 90
    assert ind.last_close == pytest.approx(100 + 89 * 1.0)
    assert ind.sma_20 == pytest.approx(sum(range(170, 190)) / 20)
    assert ind.rsi_14 == pytest.approx(100.0)
    assert ind.atr_14 == pytest.approx(4.0)   # synthetic bars have a fixed 4-wide range


def test_indicators_none_for_empty_series():
    assert compute_indicators("X.NS", []) is None


def test_short_history_keeps_real_price_but_reports_missing_indicators():
    ind = compute_indicators("X.NS", make_bars(15, base=50, step=1))
    assert ind.last_close == pytest.approx(64.0), "real close must survive a short series"
    assert ind.sma_20 is None
    assert any("insufficient history" in n for n in ind.notes)


def test_flat_series_is_neutral_not_bearish():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=0.0))
    assert trend_bias(ind) == "neutral"


def test_uptrend_and_downtrend_are_classified():
    assert trend_bias(compute_indicators("X.NS", make_bars(90, 100, 1))).startswith("bullish")
    assert trend_bias(compute_indicators("X.NS", make_bars(90, 200, -1))).startswith("bearish")


def test_technicals_text_only_states_computed_values():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=0.5))
    text = " ".join(describe_technicals(ind))
    assert f"{ind.sma_20:.1f}" in text
    assert f"{ind.rsi_14:.1f}" in text
    assert f"{ind.atr_14:.2f}" in text


# ---------------------------------------------------------------------------
# Derived trade levels
# ---------------------------------------------------------------------------

def test_levels_are_deterministic():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=0.5))
    first = derive_levels(ind, "LONG")
    second = derive_levels(ind, "LONG")
    assert first.as_dict() == second.as_dict()


def test_long_levels_are_ordered_and_risk_reward_recomputed():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=0.5))
    levels = derive_levels(ind, "LONG")
    assert levels.valid
    assert levels.target > levels.entry > levels.stop
    risk = levels.entry - levels.stop
    reward = levels.target - levels.entry
    assert levels.risk_reward == pytest.approx(round(reward / risk, 2))


def test_short_levels_are_inverted():
    ind = compute_indicators("X.NS", make_bars(90, base=200, step=-0.5))
    levels = derive_levels(ind, "SHORT")
    assert levels.valid
    assert levels.target < levels.entry < levels.stop


def test_entry_equals_the_real_reference_price():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=0.5))
    levels = derive_levels(ind, "LONG")
    assert levels.entry == pytest.approx(ind.last_close)
    assert levels.entry == pytest.approx(levels.reference_price)


def test_missing_price_rejects_rather_than_defaults():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=0.5))
    ind.last_close = 0.0
    levels = derive_levels(ind, "LONG")
    assert levels.valid is False
    assert levels.entry == 0 and levels.target == 0 and levels.stop == 0
    assert "no real price" in levels.invalid_reason


def test_insufficient_history_rejects_rather_than_defaults():
    ind = compute_indicators("X.NS", make_bars(15, base=100, step=1))
    levels = derive_levels(ind, "LONG")
    assert levels.valid is False
    assert "insufficient history" in levels.invalid_reason


def test_missing_atr_rejects():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=0.5))
    ind.atr_14 = None
    assert derive_levels(ind, "LONG").valid is False


def test_risk_is_capped():
    ind = compute_indicators("X.NS", make_bars(90, base=100, step=0.5))
    levels = derive_levels(ind, "LONG", max_risk_pct=12.0)
    assert levels.risk_pct <= 12.0


# ---------------------------------------------------------------------------
# Indian market identification
# ---------------------------------------------------------------------------

def test_indian_tickers_normalise_to_nse_or_bse():
    assert normalise_ticker("RELIANCE") == "RELIANCE.NS"
    assert normalise_ticker("LUPIN.BO") == "LUPIN.BO"
    assert normalise_ticker("reliance") == "RELIANCE.NS"


def test_explicit_foreign_listings_are_rejected():
    for foreign in ("VOD.L", "7203.T", "SAP.DE", "000001.SS"):
        assert normalise_ticker(foreign) is None, f"{foreign} must not be treated as Indian"


# ---------------------------------------------------------------------------
# Session awareness (IST)
# ---------------------------------------------------------------------------

def test_four_am_run_is_labelled_previous_close():
    """The production 04:00 IST run must never claim a live price."""
    status = market_status(datetime(2026, 10, 5, 4, 0, tzinfo=IST))
    assert status.price_kind == "previous_close"
    assert status.is_live is False


def test_seven_am_run_is_labelled_previous_close():
    status = market_status(datetime(2026, 10, 5, 7, 0, tzinfo=IST))
    assert status.price_kind == "previous_close"


def test_mid_session_is_live():
    status = market_status(datetime(2026, 10, 5, 11, 0, tzinfo=IST))
    assert status.session == "OPEN"
    assert status.price_kind == "live"
    assert status.is_live


def test_weekend_and_holiday_are_distinguished():
    assert market_status(datetime(2026, 10, 3, 10, 0, tzinfo=IST)).session == "WEEKEND"
    assert market_status(datetime(2026, 10, 2, 10, 0, tzinfo=IST)).session == "HOLIDAY"


def test_previous_trading_day_skips_the_weekend():
    # Monday 5 Oct 2026 -> previous trading day is Thursday 1 Oct
    assert previous_trading_day(datetime(2026, 10, 5).date()) == datetime(2026, 10, 1).date()


# ---------------------------------------------------------------------------
# No fabricated fallback anywhere in the market layer
# ---------------------------------------------------------------------------

def test_client_returns_none_when_price_is_unavailable(monkeypatch):
    from src.market.quotes import MarketDataClient

    client = MarketDataClient()

    class FakeTicker:
        def __init__(self, *_a, **_k):
            self.info = {}
        def history(self, **_k):
            return None

    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    monkeypatch.setattr(client, "_lazy_yf", lambda: yf)

    assert client.get_quote("NOSUCH.NS") is None
    assert client.get_market_snapshot("NOSUCH.NS") is None


def test_zero_price_is_never_substituted(monkeypatch):
    from src.market.quotes import MarketDataClient

    client = MarketDataClient()

    class FakeTicker:
        def __init__(self, *_a, **_k):
            self.info = {"regularMarketPrice": 0, "regularMarketPreviousClose": 0}
        def history(self, **_k):
            return None

    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", FakeTicker)
    monkeypatch.setattr(client, "_lazy_yf", lambda: yf)

    assert client.get_quote("ZEROPRICE.NS") is None
