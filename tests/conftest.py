"""Shared fixtures and fakes.

Everything external is faked here on purpose: these tests must be able to run
with no network, no API keys and no Telegram. The real integrations are
verified separately by ``tests/test_live_optional.py``, which skips when
credentials are absent.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.market.indicators import compute_indicators  # noqa: E402
from src.market.quotes import Quote  # noqa: E402
from src.market.session import IST, market_status  # noqa: E402
from src.tickers import Resolution  # noqa: E402


def make_bars(count: int = 90, base: float = 100.0, step: float = 0.5):
    """Deterministic synthetic OHLCV series."""
    start = datetime(2026, 1, 1)
    return [
        {
            "timestamp": start + timedelta(days=i),
            "open": base + step * i,
            "high": base + step * i + 2,
            "low": base + step * i - 2,
            "close": base + step * i,
            "volume": 500_000.0,
        }
        for i in range(count)
    ]


def now_ist() -> datetime:
    return datetime.now(IST)


def hours_ago(hours: float) -> str:
    return (now_ist() - timedelta(hours=hours)).isoformat()


def article(title: str, url: str, *, source: str = "test_source", tier: int = 2,
            published: str | None = "2h", body: str | None = None) -> dict:
    """Build a scraped-article dict.

    ``published`` accepts an ISO timestamp, ``"Nh"`` for N hours ago, or
    ``""``/``None`` for a deliberately missing timestamp.
    """
    if published in (None, ""):
        published_at = ""
    elif isinstance(published, str) and published.endswith("h") and published[:-1].isdigit():
        published_at = hours_ago(float(published[:-1]))
    else:
        published_at = published
    return {
        "title": title,
        "url": url,
        "source": source,
        "tier": tier,
        "published": published_at,
        "content": body or (title + ". ") * 20,
        "summary": title,
    }


class FakeMarketClient:
    """Stands in for MarketDataClient with real indicator maths."""

    def __init__(self, price: float = 140.0, available: bool = True):
        self.price = price
        self.available = available
        self.quoted: list[str] = []

    def get_quote(self, ticker: str):
        self.quoted.append(ticker)
        if not self.available:
            return None
        return Quote(
            ticker=ticker, exchange="NSE", company_name="Fake Corp Ltd",
            price=self.price, prev_close=self.price - 1.5,
            market_cap_cr=4200.0, volume=400_000.0, source="fake-feed",
            price_kind="previous_close",
            session_label="Pre-open - previous close (01 Oct 2026)",
            as_of="2026-10-01T15:30:00+05:30",
        )

    def get_market_snapshot(self, ticker: str):
        quote = self.get_quote(ticker)
        if quote is None:
            return None
        # Align the bar series with the quote so entry == real price.
        bars = make_bars(count=90, base=self.price - 0.5 * 89, step=0.5)
        indicators = compute_indicators(ticker, bars, source="fake-feed")
        return {"quote": quote, "indicators": indicators, "session": market_status()}


class FakeResolver:
    def __init__(self, ticker: str = "FAKECORP.NS", company: str = "Fake Corp Ltd",
                 verified: bool = True):
        self.ticker, self.company, self.verified = ticker, company, verified
        self.requested: list[str] = []

    def resolve_from_text(self, text: str):
        self.requested.append(text)
        if "fakecorp" not in text.lower():
            return []
        return [Resolution(self.ticker, self.company, "alias", self.verified, "fake")]


class FakeAI:
    """Returns a canned assessment, and records that it was asked."""

    def __init__(self, material: bool = True, relevance: int = 82):
        self.material = material
        self.relevance = relevance
        self.calls: list[str] = []
        self.fail = False

    def ask_json(self, system: str, prompt: str, **kwargs):
        self.calls.append(prompt)
        if self.fail:
            return None
        if "Assess this news article" in prompt:
            if not self.material:
                return {"is_material": False, "rejection_reason": "NOT_MATERIAL"}
            return {
                "is_material": True,
                "event_type": "ORDER_WIN",
                "direction": "LONG",
                "relevance_score": self.relevance,
                "time_horizon_days": 7,
                "why_it_matters": "Order strengthens the order book.",
                "key_risk": "Order may not convert to revenue.",
                "catalyst_summary": "Bagged a Rs 500 crore order.",
            }
        return {
            "thesis": "Order visibility supports the next quarter.",
            "watchpoint": "Order conversion in the next filing.",
            "evidence": "The article states the award.",
        }


@pytest.fixture
def store(tmp_path):
    from src.store import get_store, reset_store

    reset_store()
    instance = get_store(force="git", root=tmp_path)
    yield instance
    reset_store()


@pytest.fixture
def market():
    return FakeMarketClient()


@pytest.fixture
def resolver():
    return FakeResolver()


@pytest.fixture
def ai():
    return FakeAI()


@pytest.fixture
def pipeline_factory(store, market, resolver, ai):
    from src.pipeline.news_signal import NewsSignalPipeline

    def build(**kwargs):
        params = dict(
            store=store, market=market, resolver=resolver, ai=ai,
            max_signals=3, freshness_hours=30,
        )
        params.update(kwargs)
        return NewsSignalPipeline(**params)

    return build
