"""Requirement 15 and the "does it find new stocks?" question.

The curated lookup tables cover ~450 well-known names. These tests prove that a
company *absent* from every table is still discovered and, crucially, only
accepted once a real NSE/BSE listing with a real price confirms it.
"""
from __future__ import annotations

import pytest

from src.pipeline.news_signal import NewsSignalPipeline
from src.tickers import Resolution, TickerResolver, get_resolver
from tests.conftest import FakeAI, FakeMarketClient, article


class DiscoveryAI(FakeAI):
    """Answers both the assessment prompt and the company-discovery prompt."""

    def __init__(self, propose=("Obscure Infra Ltd",), **kw):
        super().__init__(**kw)
        self.propose = list(propose)
        self.discovery_prompts = []

    def ask_json(self, system, prompt, **kw):
        if "Which of these organisations" in prompt:
            self.discovery_prompts.append(prompt)
            return {"companies": list(self.propose)}
        return super().ask_json(system, prompt, **kw)


class DiscoveryResolver(TickerResolver):
    """Knows one obscure company only via *live verification*.

    ``propose`` returns nothing for it, exactly like a name missing from the
    config tables; ``_confirm`` is where it becomes real.
    """

    def __init__(self, ticker="OBSCURE.NS", company="Obscure Infra Ltd"):
        super().__init__(verify_live=True)
        self.ticker, self.company = ticker, company
        self.confirm_calls = []

    def propose(self, name):
        # Deliberately not in the lookup tables: discovery must do the work.
        return Resolution(self.ticker, name.strip(), "discovered", verified=False)

    def _confirm(self, resolution):
        self.confirm_calls.append(resolution.company_name)
        return Resolution(resolution.ticker, self.company, "discovered",
                          verified=True, note="confirmed live")

    def resolve_from_text(self, text):
        # Stage 1 finds nothing in the curated tables.
        return []


def test_curated_tables_alone_do_not_find_an_unknown_company():
    """Baseline: proves discovery is what closes the gap."""
    resolver = TickerResolver(verify_live=False)
    assert resolver.resolve_from_text(
        "Obscure Infra Ltd signed a Rs 400 crore order."
    ) == []


def test_unknown_company_is_discovered_and_verified(store):
    market = FakeMarketClient()
    resolver = DiscoveryResolver()
    ai = DiscoveryAI()
    pipeline = NewsSignalPipeline(
        store, market=market, resolver=resolver, ai=ai, max_signals=3,
    )
    signals = pipeline.run([article(
        "Obscure Infra Ltd wins Rs 400 crore order",
        "https://economictimes.indiatimes.com/news/obscure.cms",
    )])
    assert len(signals) == 1, "an unlisted-in-config company should still be found"
    assert signals[0]["ticker"] == "OBSCURE.NS"
    assert resolver.confirm_calls, "the name must be confirmed against a real listing"


def test_discovery_is_attempted_once_per_story(store):
    resolver = DiscoveryResolver()
    pipeline = NewsSignalPipeline(
        store, market=FakeMarketClient(), resolver=resolver,
        ai=DiscoveryAI(), max_signals=3,
    )
    pipeline.run([article(
        "Obscure Infra Ltd wins Rs 400 crore order",
        "https://economictimes.indiatimes.com/news/obscure.cms",
    )])
    before = len(resolver.confirm_calls)
    pipeline._resolve_companies(_candidate(pipeline))
    assert len(resolver.confirm_calls) == before, "same story must not be re-asked"


def _candidate(pipeline):
    from src.pipeline.news_signal import Candidate
    from src.news.fingerprint import canonical_url, story_key_for

    c = Candidate(
        title="Obscure Infra Ltd wins Rs 400 crore order",
        url="https://economictimes.indiatimes.com/news/obscure.cms",
        canonical_url=canonical_url(
            "https://economictimes.indiatimes.com/news/obscure.cms"),
        source="economic_times", tier=2, published_at=None,
    )
    c.story_key = story_key_for(c.title, c.url)
    return c


def test_a_hallucinated_company_is_rejected(store):
    """If verification fails, there must be no signal - never a made-up ticker."""
    class RejectingResolver(TickerResolver):
        def resolve_from_text(self, text):
            return []

        def resolve(self, name):
            return None      # nothing verifies as an Indian listing

    pipeline = NewsSignalPipeline(
        store, market=FakeMarketClient(), resolver=RejectingResolver(),
        ai=DiscoveryAI(propose=["Totally Fictional Systems Ltd"]), max_signals=3,
    )
    signals = pipeline.run([article(
        "Totally Fictional Systems Ltd wins Rs 900 crore defence order",
        "https://economictimes.indiatimes.com/news/fictional.cms",
    )])
    assert signals == [], "an unverifiable company must produce nothing"


def test_entity_extraction_skips_government_and_noise_tokens():
    names = NewsSignalPipeline._candidate_entity_names(
        "SEBI and RBI told NSE that GST revenue rose 12% in Q2 FY27 for Tata Motors"
    )
    assert "Tata" in names or "Motors" in names
    for noise in ("SEBI", "RBI", "NSE", "GST", "Q2", "FY27"):
        assert noise not in names, f"{noise} should not be offered as a company"


def test_micro_cap_listing_is_not_a_signal_candidate(store):
    """A real but tiny listing must not become a signal.

    Name search surfaced `PERSISTENT.NS` in a live run - a genuine micro-cap
    whose name happened to resemble the query. Real is not the same as
    tradeable.
    """
    class TinyMarket(FakeMarketClient):
        def get_quote(self, ticker):
            quote = super().get_quote(ticker)
            if quote:
                quote.market_cap_cr = 8.0
            return quote

    pipeline = NewsSignalPipeline(
        store, market=TinyMarket(), resolver=DiscoveryResolver(),
        ai=DiscoveryAI(), max_signals=3,
    )
    assert pipeline.run([article(
        "Obscure Infra Ltd wins Rs 400 crore order",
        "https://economictimes.indiatimes.com/news/obscure.cms",
    )]) == []
    assert pipeline.stats.rejected_microcap == 1
