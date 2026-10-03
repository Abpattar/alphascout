"""Requirement 13: news quality - opinion pieces must not become signals.

The first live dry-run produced three signals, all of them analyst
recommendations and dividend listicles scoring 55-58. That is the failure this
file locks down.
"""
from __future__ import annotations

import pytest

from datetime import datetime, timedelta

from src.market.session import IST
from src.pipeline.news_signal import (
    MIN_RELEVANCE_SCORE,
    NON_CATALYST_EVENT_TYPES,
    looks_like_noise,
)
from tests.conftest import article


@pytest.mark.parametrize("headline", [
    "Vaishali Parekh's top 3 stocks to buy: CG Power, Graphite India, Bectors Food",
    "Dividend jackpot shares: Coal India, Wipro, ITC, BPCL or ONGC? Which has the highest yield?",
    "Policybazaar, Paisabazaar share down 48% in 6 days - Here's why",
    "5 stocks to watch for the week ahead",
    "Sensex sheds 571 points as bears tighten grip, Nifty below 22,500",
    "Multibagger stock: HFCL shares hit 5% upper circuit",
    "Should you buy these stocks now?",
    "Market outlook for the coming week",
    "Top 10 gainers of the day",
])
def test_opinion_and_listicle_headlines_are_noise(headline):
    assert looks_like_noise(headline) is not None, f"should have been filtered: {headline}"


@pytest.mark.parametrize("headline", [
    "Lupin wins Rs 1,000 crore USFDA approval for new plant",
    "SEBI orders Paras Defence to pay Rs 250 crore penalty",
    "Infosys signs Rs 5,000 crore deal with Bank of Baroda",
    "Tata Power board approves Rs 1,200 crore capex for new plant",
    "Coal India Q2 profit rises 18 percent, declares interim dividend",
    "Bharat Dynamics wins Rs 900 crore naval contract",
    "Reliance arm acquires assets for Rs 2,000 crore",
    "Hindustan Aeronautics reports order book of Rs 1 lakh crore",
])
def test_genuine_catalysts_are_not_treated_as_noise(headline):
    assert looks_like_noise(headline) is None, f"wrongly filtered: {headline}"


def test_noise_patterns_are_not_over_broad():
    """A real order win must survive even when it mentions many numbers."""
    assert looks_like_noise("HAL bags Rs 1,200 crore order for 36 radars") is None
    assert looks_like_noise("Company X wins 3 orders worth Rs 450 crore") is None


# ---------------------------------------------------------------------------
# End-to-end: noise never reaches the AI
# ---------------------------------------------------------------------------

def test_noise_articles_never_reach_the_ai(pipeline_factory, ai):
    pipeline = pipeline_factory()
    pipeline.run([
        article("Vaishali Parekh's top 3 stocks to buy: Graphite India and others",
                "https://a.example/1"),
        article("5 stocks to watch for the week ahead", "https://a.example/2"),
        article("Fakecorp wins Rs 1,000 crore USFDA approval for new plant",
                "https://a.example/3"),
    ])
    assert pipeline.stats.articles_noise == 2
    assert pipeline.stats.ai_assessed == 1, "only the real catalyst should cost an LLM call"


def test_low_relevance_is_rejected(pipeline_factory, market, resolver, store):
    from src.ai.client import AIClient
    from src.pipeline.news_signal import NewsSignalPipeline
    from tests.conftest import FakeAI

    weak = FakeAI(relevance=40)
    pipeline = NewsSignalPipeline(
        store, market=market, resolver=resolver, ai=weak, max_signals=3,
    )
    assert pipeline.run([article(
        "Fakecorp wins Rs 1,000 crore USFDA approval", "https://a.example/1",
    )]) == []
    assert pipeline.stats.rejected_low_relevance == 1


def test_research_event_type_is_not_a_catalyst(pipeline_factory, market, resolver, store):
    from src.pipeline.news_signal import NewsSignalPipeline
    from tests.conftest import FakeAI

    class ResearchAI(FakeAI):
        def ask_json(self, system, prompt, **kw):
            result = super().ask_json(system, prompt, **kw)
            if result and "Assess this news article" in prompt:
                result["event_type"] = "RESEARCH"
                result["relevance_score"] = 90
            return result

    pipeline = NewsSignalPipeline(
        store, market=market, resolver=resolver, ai=ResearchAI(), max_signals=3,
    )
    assert pipeline.run([article(
        "Brokerage upgrades Fakecorp with a buy rating and reiterates buy",
        "https://a.example/1",
    )]) == []
    assert pipeline.stats.rejected_non_catalyst == 1


def test_relevance_floor_is_not_token():
    """The default must actually exclude the 55-58 band seen in the live run."""
    assert MIN_RELEVANCE_SCORE >= 60
    assert "RESEARCH" in NON_CATALYST_EVENT_TYPES


def test_neutral_direction_does_not_become_a_long_trade(pipeline_factory, market, resolver, store):
    """A material but non-directional story must not be dressed up as a LONG."""
    from src.pipeline.news_signal import NewsSignalPipeline
    from tests.conftest import FakeAI

    class NeutralAI(FakeAI):
        def ask_json(self, system, prompt, **kw):
            result = super().ask_json(system, prompt, **kw)
            if result and "Assess this news article" in prompt:
                result["direction"] = "NEUTRAL"
            return result

    pipeline = NewsSignalPipeline(
        store, market=market, resolver=resolver, ai=NeutralAI(), max_signals=3,
    )
    assert pipeline.run([article(
        "Fakecorp Q2 profit rises 22 percent", "https://a.example/1",
    )]) == []
    assert pipeline.stats.rejected_non_directional == 1


def test_dry_run_leaves_no_state(monkeypatch, tmp_path):
    """A dry run must not create history or cooldown entries."""
    import asyncio

    from src.store import get_store, reset_store
    from tests.conftest import FakeAI, FakeMarketClient, FakeResolver
    from src.pipeline import runner

    reset_store()
    store = get_store(force="git", root=tmp_path)
    article_row = {
        "title": "Fakecorp wins Rs 500 crore order",
        "url": "https://a.example/1", "source": "s", "tier": 2,
        "published": (datetime.now(IST) - timedelta(hours=1)).isoformat(),
        "content": "Fakecorp wins an order. " * 20, "summary": "x",
    }
    monkeypatch.setattr("src.scraping.scraper.scrape_all_sources",
                        lambda **kw: [article_row])
    monkeypatch.setattr(runner, "TICKER_ALLOWLIST", None, raising=False)

    real_get = runner.get_store if hasattr(runner, "get_store") else None
    import src.pipeline.runner as rmod
    monkeypatch.setattr(rmod, "get_store", lambda *a, **k: store, raising=False)
    monkeypatch.setattr(rmod, "MarketDataClient", FakeMarketClient, raising=False)
    monkeypatch.setattr(rmod, "get_market_client", FakeMarketClient, raising=False)
    monkeypatch.setattr("src.tickers.get_resolver", FakeResolver, raising=False)

    report = asyncio.run(rmod.run(dry_run=True, max_signals=3))
    reset_store()

    assert store.counts()["articles"] == 0, "dry run must not persist articles"
    assert store.counts()["signals"] == 0, "dry run must not persist signals"
    assert store.sent_story_keys() == set()
