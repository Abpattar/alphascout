"""Requirement 17: the validation gate, and requirement 18: Telegram output.

The Telegram tests use deliberately hostile content - ``<``, ``&``, quotes,
emoji, very long strings - because that is exactly what broke message delivery
before (HTTP 400, signal silently lost).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests.conftest import article, hours_ago, make_bars
from src.market.indicators import compute_indicators, derive_levels
from src.market.quotes import Quote
from src.market.session import IST, market_status, now_ist
from src.portfolio.formatter import format_run_footer, format_signal
from src.tickers import Resolution
from src.validation import SignalValidator


# ---------------------------------------------------------------------------
# Validation gate
# ---------------------------------------------------------------------------

def _parts(ticker="FAKECORP.NS", price=140.0, verified=True, **overrides):
    quote = Quote(
        ticker=ticker, exchange="NSE", company_name="Fake Corp Ltd",
        price=price, prev_close=price - 1.5, market_cap_cr=4200.0,
        volume=1e5, source="test-feed", price_kind="previous_close",
        session_label="Pre-open", as_of="2026-10-01T15:30:00+05:30",
    )
    bars = make_bars(90, base=price - 0.5 * 89, step=0.5)
    indicators = compute_indicators(ticker, bars, source="test-feed")
    levels = derive_levels(indicators, "LONG")
    article_dict = article("Fakecorp wins Rs 500 crore order", "https://x.example/a")
    # The pipeline hands the validator the normalised key.
    article_dict["published_at"] = article_dict.get("published", "")
    article_dict["canonical_url"] = article_dict["url"]
    resolution = Resolution(ticker, "Fake Corp Ltd", "alias", verified, "test")
    signal = {
        "ticker": ticker,
        "ai": {"thesis": "Order supports backlog.", "risk": "May not convert."},
    }
    signal.update(overrides)
    return dict(
        signal=signal, article=article_dict, quote=quote,
        indicators=indicators, levels=levels, resolution=resolution,
        store=None, freshness_window_hours=30,
    )


def test_valid_signal_passes():
    assert SignalValidator().validate(**_parts()).ok


def test_missing_market_data_is_rejected():
    parts = _parts()
    parts["quote"] = None
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("refusing to invent" in r for r in result.reasons)


def test_missing_indicators_are_rejected():
    parts = _parts()
    parts["indicators"] = None
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("indicators unavailable" in r for r in result.reasons)


def test_unverified_ticker_is_rejected():
    result = SignalValidator().validate(**_parts(verified=False))
    assert not result.ok
    assert any("not verified" in r for r in result.reasons)


def test_non_indian_ticker_is_rejected():
    result = SignalValidator().validate(**_parts(ticker="AAPL.US"))
    assert not result.ok


def test_stale_article_is_rejected():
    parts = _parts()
    parts["article"]["published_at"] = hours_ago(24 * 10)
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("freshness window" in r for r in result.reasons)


def test_article_without_timestamp_is_rejected():
    parts = _parts()
    parts["article"]["published_at"] = ""
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("cannot confirm freshness" in r for r in result.reasons)


def test_inverted_levels_are_rejected():
    parts = _parts()
    parts["levels"].target = parts["levels"].entry - 10
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("ordering violated" in r for r in result.reasons)


def test_entry_that_does_not_match_the_market_is_rejected():
    """The anti-fabrication check: entry must equal the real price."""
    parts = _parts()
    parts["levels"].entry = parts["levels"].entry * 3
    parts["levels"].reference_price = parts["levels"].entry
    result = SignalValidator().validate(**parts)
    assert not result.ok


def test_entry_far_from_market_price_is_rejected():
    parts = _parts()
    parts["levels"].entry = 500.0     # real price is 140
    parts["levels"].reference_price = 500.0
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("away from the real price" in r for r in result.reasons)


def test_invalid_levels_are_rejected():
    parts = _parts()
    parts["levels"].valid = False
    parts["levels"].invalid_reason = "no real price available"
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("could not be derived" in r for r in result.reasons)


def test_weak_risk_reward_is_rejected():
    parts = _parts()
    parts["levels"].risk_reward = 0.4
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("risk/reward" in r for r in result.reasons)


def test_ai_numeric_fields_are_rejected():
    """The model must not be able to smuggle a price into a signal."""
    for key, value in (("entry_price", 100), ("target_price", 200),
                       ("rsi_14", 68), ("technical_checklist", {"above_20dma": True})):
        parts = _parts()
        parts["signal"]["ai"][key] = value
        result = SignalValidator().validate(**parts)
        assert not result.ok, f"{key} should have been rejected"
        assert any("AI block must not contain" in r for r in result.reasons)


def test_ai_without_thesis_is_rejected():
    parts = _parts()
    parts["signal"]["ai"]["thesis"] = "   "
    result = SignalValidator().validate(**parts)
    assert not result.ok


def test_zero_price_is_rejected():
    parts = _parts()
    parts["quote"].price = 0.0
    result = SignalValidator().validate(**parts)
    assert not result.ok


def test_implausible_price_is_rejected():
    parts = _parts()
    parts["quote"].price = 99_999_999.0
    result = SignalValidator().validate(**parts)
    assert not result.ok


def test_already_sent_article_is_rejected(store):
    from src.store import ArticleRecord

    parts = _parts()
    canonical = parts["article"].get("canonical_url") or "https://x.example/a"
    store.upsert_articles([ArticleRecord(
        canonical_url=canonical, url=canonical, title="t",
        first_seen_at=now_ist().isoformat(), sent=1, status="sent",
    )])
    parts["article"]["canonical_url"] = canonical
    parts["store"] = store
    result = SignalValidator().validate(**parts)
    assert not result.ok
    assert any("already sent" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Telegram formatting
# ---------------------------------------------------------------------------

def _signal_for_format(**overrides):
    indicators = compute_indicators("FAKECORP.NS", make_bars(90, base=139.5, step=0.5))
    levels = derive_levels(indicators, "LONG")
    signal = {
        "ticker": "FAKECORP.NS",
        "exchange": "NSE",
        "company_name": "Fake Corp Ltd",
        "direction": "LONG",
        "relevance_score": 82,
        "facts": {
            "price": 140.0, "price_kind": "previous_close", "prev_close": 138.5,
            "change_pct": 1.08, "market_cap_cr": 4200.0, "price_source": "yfinance",
            "session_label": "Pre-open - previous close (01 Oct 2026)",
        },
        "calculated": {
            **levels.as_dict(), "trend": "bullish", "rsi_14": indicators.rsi_14,
            "sma_20": indicators.sma_20, "atr_14": indicators.atr_14,
        },
        "ai": {
            "thesis": "Order visibility supports the next quarter.",
            "watchpoint": "Order conversion.",
            "risk": "Order may not convert.",
            "catalyst": "Bagged a Rs 500 crore order.",
            "event_type": "ORDER_WIN",
        },
        "article": {
            "title": "Fakecorp wins Rs 500 crore order",
            "url": "https://example.com/a?x=1&y=2",
            "source": "economic_times",
            "published_at": "2026-10-03T09:00:00+05:30",
            "corroborating_sources": ["economic_times", "moneycontrol"],
        },
    }
    signal.update(overrides)
    return signal


def test_message_separates_facts_from_calculations_from_ai():
    text = format_signal(_signal_for_format())
    assert "MARKET DATA" in text
    assert "CALCULATED" in text
    assert "AI ASSESSMENT" in text
    assert "from market feed" in text
    assert "computed from real prices" in text
    assert "interpretation, not data" in text


def test_price_is_labelled_previous_close_not_live():
    text = format_signal(_signal_for_format())
    assert "PREVIOUS CLOSE" in text
    assert "LIVE" not in text.replace("LIVE", "", 0) or "(LIVE)" not in text


def test_message_shows_the_real_price():
    text = format_signal(_signal_for_format())
    assert "₹140.00" in text


def test_hostile_characters_are_escaped():
    """Regression: raw < or & made Telegram reject the whole message."""
    signal = _signal_for_format()
    signal["ai"]["thesis"] = "Buy <₹500 & hold > 20 days — R&D risk"
    signal["article"]["title"] = "Fakecorp <script>alert(1)</script> wins order"
    text = format_signal(signal)
    assert "<script>" not in text
    assert "&lt;" in text and "&amp;" in text
    assert "&lt;₹500" in text


def test_url_with_quote_cannot_break_the_attribute():
    signal = _signal_for_format()
    signal["article"]["url"] = "https://example.com/a?x='y'&z=2"
    text = format_signal(signal)
    assert "&#x27;" in text
    assert "x='y'" not in text


def test_missing_optional_fields_render_as_na_not_crash():
    signal = _signal_for_format()
    signal["calculated"].update({"rsi_14": None, "sma_20": None, "atr_14": None})
    signal["facts"].update({"prev_close": 0, "change_pct": None, "market_cap_cr": 0})
    text = format_signal(signal)
    assert "n/a" in text
    assert "₹140.00" in text


def test_long_headline_is_truncated():
    signal = _signal_for_format()
    signal["article"]["title"] = "Fakecorp " + ("wins a very large order " * 40)
    text = format_signal(signal)
    assert len(text) < 4200, "Telegram's message limit is 4096 characters"


def test_development_flag_is_shown():
    signal = _signal_for_format()
    signal["article"]["is_development"] = True
    assert "New development" in format_signal(signal)


def test_footer_explains_an_empty_run():
    text = format_run_footer(0, {"articles_scraped": 90, "articles_fresh": 4, "stories_duplicate": 12})
    assert "no qualifying new signals" in text
    assert "correct outcome" in text
    assert "90" in text


def test_footer_reports_sent_count():
    text = format_run_footer(2, {"articles_scraped": 90})
    assert "Sent" in text and "2" in text
