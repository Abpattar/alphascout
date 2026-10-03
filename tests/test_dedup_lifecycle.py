"""Requirement 21: the duplicate-news scenarios, end to end.

These are the tests that matter most: they encode the exact situations where
the previous system failed, because it had no memory between GitHub runners.

    Run 1: article A appears            -> processed and sent
    Run 2: article A appears again      -> recognised, NOT sent
    Run 2: article B appears            -> processed, may be sent
    Run 3: new development of A         -> allowed through as new information
    Cross-source: same event, 2 outlets -> merged into one story
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests.conftest import article, hours_ago

A_TITLE = "Fakecorp wins Rs 500 crore order from the defence ministry"
A_URL = "https://economictimes.indiatimes.com/news/alpha.cms"
B_TITLE = "Fakecorp board approves Rs 120 crore capital expenditure"
B_URL = "https://www.moneycontrol.com/news/business/beta.html"


# ---------------------------------------------------------------------------
# Run 1 / Run 2 / Run 3
# ---------------------------------------------------------------------------

def test_run1_article_a_is_sent(pipeline_factory):
    pipeline = pipeline_factory()
    signals = pipeline.run([article(A_TITLE, A_URL)])
    assert len(signals) == 1, "article A should produce a signal on first sight"
    assert signals[0]["ticker"] == "FAKECORP.NS"
    pipeline.persist(signals)
    pipeline.mark_sent(signals)


def test_run2_article_a_is_not_resent(pipeline_factory):
    """The same story on a later run must be suppressed.

    Uses a *fresh pipeline instance* against the *same store*, which is exactly
    what a second GitHub Actions run looks like.
    """
    first = pipeline_factory()
    signals = first.run([article(A_TITLE, A_URL)])
    assert len(signals) == 1
    first.persist(signals)
    first.mark_sent(signals)

    second = pipeline_factory()          # new process, same persistent store
    again = second.run([article(A_TITLE, A_URL, published="3h")])
    assert again == [], "article A must not be sent twice"
    assert second.stats.stories_duplicate == 1
    assert second.stats.sent == 0


def test_run2_article_a_same_url_different_tracking_params(pipeline_factory):
    """Tracking parameters must not defeat deduplication."""
    first = pipeline_factory()
    signals = first.run([article(A_TITLE, A_URL)])
    first.persist(signals)
    first.mark_sent(signals)

    second = pipeline_factory()
    noisy = A_URL + "?utm_source=twitter&utm_medium=social&ref=newsletter"
    assert second.run([article(A_TITLE, noisy)]) == []


def test_run2_article_b_is_still_allowed(pipeline_factory_multi):
    """Suppressing A must not suppress an unrelated story from another company."""
    first = pipeline_factory_multi()
    a_signals = first.run([article(A_TITLE, A_URL)])
    first.persist(a_signals)
    first.mark_sent(a_signals)

    second = pipeline_factory_multi()
    b_signals = second.run([
        article(A_TITLE, A_URL, published="3h"),          # already delivered
        article("Othercorp wins Rs 800 crore air-defence order",
                "https://www.moneycontrol.com/news/other.html"),
    ])
    assert len(b_signals) == 1, "only the new company should get through"
    assert b_signals[0]["ticker"] == "OTHER.NS"
    assert second.stats.stories_duplicate == 1


def test_recent_ticker_is_deprioritised_not_blocked(pipeline_factory_multi):
    """A new, different story about a just-signalled company is still sent.

    The per-ticker cooldown only affects ranking. Blocking here would discard
    genuinely new material news, which the product explicitly requires us to
    allow; ranking keeps the three daily slots spread across companies.
    """
    first = pipeline_factory_multi()
    signals = first.run([article(A_TITLE, A_URL)])
    first.persist(signals)
    first.mark_sent(signals)

    second = pipeline_factory_multi()
    later = second.run([article(
        "Fakecorp receives SEBI show-cause notice",
        "https://economictimes.indiatimes.com/news/other.cms",
    )])
    assert len(later) == 1, "new material news must not be silently dropped"
    assert later[0].get("_recently_sent") is True


def test_ranking_prefers_a_company_we_have_not_just_messaged_about(pipeline_factory_multi):
    """With more candidates than slots, fresh tickers win the limited slots."""
    first = pipeline_factory_multi()
    signals = first.run([article(A_TITLE, A_URL)])
    first.persist(signals)
    first.mark_sent(signals)

    second = pipeline_factory_multi(max_signals=1)
    ranked = second.run([
        article(A_TITLE.replace("Fakecorp", "Alphacorp"),
                "https://economictimes.indiatimes.com/news/a2.cms"),
        article("Betacorp wins Rs 800 crore air-defence order",
                "https://economictimes.indiatimes.com/news/b2.cms"),
    ])
    assert len(ranked) == 1
    assert ranked[0]["ticker"] == "BETA.NS", "the never-signalled ticker should win"


def test_run3_new_development_is_allowed(pipeline_factory):
    """A follow-up with a fresh action and a new figure is new information."""
    first = pipeline_factory()
    signals = first.run([article(
        "Fakecorp receives regulatory notice from SEBI", A_URL,
    )])
    assert len(signals) == 1
    first.persist(signals)
    first.mark_sent(signals)

    second = pipeline_factory()
    follow_up = article(
        "SEBI orders Fakecorp to pay Rs 250 crore penalty for disclosure lapse",
        "https://economictimes.indiatimes.com/news/gamma.cms",
        published="1h",
    )
    signals = second.run([follow_up])
    assert len(signals) == 1, "a genuine new development must not be suppressed"
    assert signals[0]["article"]["is_development"] is True
    assert second.stats.stories_development == 1


def test_repeat_without_new_information_is_suppressed(pipeline_factory):
    """A rewording of the same development is not new information."""
    first = pipeline_factory()
    signals = first.run([article(
        "SEBI orders Fakecorp to pay Rs 250 crore penalty", A_URL,
    )])
    first.persist(signals)
    first.mark_sent(signals)

    second = pipeline_factory()
    assert second.run([article(
        "SEBI orders Fakecorp to pay Rs 250 crore penalty",
        "https://www.moneycontrol.com/news/business/dup.html",
        published="1h",
    )]) == []


# ---------------------------------------------------------------------------
# Cross-source dedup
# ---------------------------------------------------------------------------

def test_two_outlets_same_event_produce_one_signal(pipeline_factory):
    pipeline = pipeline_factory()
    articles = [
        article("Fakecorp announces Rs 10,000 crore investment",
                "https://economictimes.indiatimes.com/news/x1.cms",
                source="economic_times", tier=2),
        article("Fakecorp to invest Rs 10000 crore in expansion",
                "https://www.moneycontrol.com/news/x2.html",
                source="moneycontrol_markets", tier=2),
    ]
    signals = pipeline.run(articles)
    assert len(signals) == 1
    sources = signals[0]["article"]["corroborating_sources"]
    assert set(sources) == {"economic_times", "moneycontrol_markets"}


def test_two_outlets_merged_before_any_llm_spend(pipeline_factory):
    """Clustering must happen upstream of the AI so we do not pay twice."""
    pipeline = pipeline_factory()
    pipeline.run([
        article("Fakecorp announces Rs 10,000 crore investment",
                "https://a.example/1", source="s1"),
        article("Fakecorp to invest Rs 10000 crore in expansion",
                "https://b.example/2", source="s2"),
    ])
    assert pipeline.stats.stories_clustered == 1
    assert pipeline.stats.ai_assessed == 1


def test_unrelated_events_same_company_are_not_merged(pipeline_factory):
    pipeline = pipeline_factory()
    articles = [
        article("Fakecorp wins Rs 500 crore defence order", "https://a.example/1"),
        article("Fakecorp Q2 profit rises 22 percent", "https://b.example/2"),
        article("Fakecorp board approves dividend", "https://c.example/3"),
    ]
    pipeline.run(articles)
    assert pipeline.stats.stories_clustered == 3, "these are three distinct stories"


def test_same_ticker_produces_at_most_one_signal_per_run(pipeline_factory):
    pipeline = pipeline_factory()
    articles = [
        article("Fakecorp wins Rs 500 crore defence order", "https://a.example/1"),
        article("Fakecorp bags Rs 900 crore naval contract", "https://b.example/2"),
    ]
    signals = pipeline.run(articles)
    tickers = [s["ticker"] for s in signals]
    assert len(tickers) == len(set(tickers)), "one signal per ticker per run"


# ---------------------------------------------------------------------------
# Persistence really is durable
# ---------------------------------------------------------------------------

def test_state_survives_a_new_store_instance(tmp_path):
    from src.store import ArticleRecord, SignalRecord, StoryRecord, get_store, reset_store

    reset_store()
    first = get_store(force="git", root=tmp_path)
    now_iso = "2026-10-03T04:00:00+00:00"
    first.upsert_articles([ArticleRecord(
        canonical_url="https://x.example/a", title="T", first_seen_at=now_iso,
        sent=1, status="sent", story_key="k1",
    )])
    first.upsert_stories([StoryRecord(
        story_key="k1", first_seen_at=now_iso, last_seen_at=now_iso, sent_count=1,
    )])
    first.record_signals([SignalRecord(
        signal_id="s1", ticker="AAA.NS", generated_at=now_iso, market_price=100.0,
    )])
    first.flush()
    reset_store()

    second = get_store(force="git", root=tmp_path)
    assert second.get_article("https://x.example/a").sent == 1
    assert second.sent_story_keys() == {"k1"}
    assert second.counts()["signals"] == 1
    reset_store()


def test_marking_sent_is_required_for_suppression(pipeline_factory):
    """Persisting without marking sent must NOT suppress - only real sends do."""
    pipeline = pipeline_factory()
    signals = pipeline.run([article(A_TITLE, A_URL)])
    pipeline.persist(signals)          # note: no mark_sent

    second = pipeline_factory()
    assert len(second.run([article(A_TITLE, A_URL, published="4h")])) == 1


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------

def test_old_article_is_rejected(pipeline_factory):
    pipeline = pipeline_factory()
    signals = pipeline.run([article(A_TITLE, A_URL, published=hours_ago(24 * 9))])
    assert signals == []
    assert pipeline.stats.articles_stale == 1


def test_article_without_timestamp_is_not_treated_as_new(pipeline_factory):
    """No trustworthy timestamp means not-new, not "probably fine"."""
    pipeline = pipeline_factory()
    signals = pipeline.run([article(A_TITLE, A_URL, published="")])
    assert signals == []
    assert pipeline.stats.articles_no_timestamp == 1


def test_future_timestamp_is_rejected(pipeline_factory):
    from src.market.session import IST
    future = (datetime_now_ist() + timedelta(days=2)).isoformat()
    pipeline = pipeline_factory()
    assert pipeline.run([article(A_TITLE, A_URL, published=future)]) == []


def datetime_now_ist():
    from src.market.session import now_ist

    return now_ist()


# ---------------------------------------------------------------------------
# Quota behaviour
# ---------------------------------------------------------------------------

def test_never_exceeds_three_signals(pipeline_factory):
    pipeline = pipeline_factory(max_signals=99)
    assert pipeline.max_signals <= 3, "hard cap must be enforced internally"


def test_sends_nothing_when_nothing_qualifies(pipeline_factory):
    pipeline = pipeline_factory()
    assert pipeline.run([]) == []
    assert pipeline.run([article("Old thing", A_URL, published=hours_ago(24 * 30))]) == []


def test_sent_signal_rows_are_flagged_so_cooldown_works(pipeline_factory, store):
    """Regression: cooldown reads SignalRecord.sent.

    If persist() writes rows but mark_sent() never sets `sent`, the 48h
    per-ticker cooldown is silently dead - the same class of defect as the
    empty-database problem this rewrite set out to fix.
    """
    pipeline = pipeline_factory()
    signals = pipeline.run([article(A_TITLE, A_URL)])
    assert signals
    assert pipeline.persist(signals) == 1
    pipeline.mark_sent(signals)

    sent = [s for s in store.recent_signals(days=1, limit=50) if s.sent]
    assert sent, "signal rows must be flagged sent after delivery"
    assert sent[0].ticker == "FAKECORP.NS"
