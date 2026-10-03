"""The production news-to-signal pipeline.

Replaces the previous four-stage LLM pipeline, whose trade prices and
technical indicators were produced by the model. The shape now is:

    scrape -> filter for freshness -> resolve verified Indian tickers
           -> cluster into stories -> check persistent history (dedup)
           -> rank candidates -> AI assessment (prose + labels only)
           -> real market data -> deterministic levels -> validation
           -> at most MAX_SIGNALS_PER_RUN

Ordering matters and is deliberate:

* **freshness and dedup happen before any LLM call**, so we never pay for
  news we are going to discard;
* **market data is fetched before the model is asked for a view**, so the
  model reasons about real prices and cannot influence them;
* **validation runs last** and can only veto.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

from src.ai import interpret
from src.ai.client import AIClient
from src.market.indicators import (
    derive_levels,
    describe_technicals,
    trend_bias,
    volatility_score,
)
from src.market.quotes import MarketDataClient, get_client as get_market_client
from src.market.session import IST, market_status
from src.news.fingerprint import (
    canonical_url,
    content_fingerprint,
    is_new_development,
    same_story,
    story_key_for,
    title_fingerprint,
    title_similarity,
    topic_tokens,
)
from src.store import ArticleRecord, SignalRecord, StoryRecord, StoryStore, utcnow
from src.tickers import Resolution, get_resolver
from src.validation import SignalValidator

logger = logging.getLogger(__name__)

# Hard ceiling from the product requirement. Never exceeded.
MAX_SIGNALS_PER_RUN = 3

# Article-level gate before any AI spend.
DEFAULT_FRESHNESS_HOURS = 30
MIN_ARTICLE_CHARS = 120
# Minimum AI relevance score. Deliberately well above the midpoint: a story
# must be a real catalyst, not merely interesting.
MIN_RELEVANCE_SCORE = 62

# Per-ticker brake. Deliberately short. Repeats are already suppressed at
# story level, so this only needs to stop a burst about one stock; a long
# window would wrongly mute genuinely new news about a company signalled
# earlier the same day. New developments bypass it entirely.
DEFAULT_TICKER_COOLDOWN_HOURS = 12

# Event types that are commentary about the market rather than news about a
# company. An analyst's "top 3 stocks to buy" is a view, not an event, and
# acting on it means trading on someone else's opinion.
NON_CATALYST_EVENT_TYPES = {"RESEARCH", "OTHER"}

# Headline shapes that are listicles or opinion pieces. These dominate market
# wraps and say nothing about a specific company's situation.
_NOISE_PATTERNS = [
    # "top 3 stocks to buy", "top 10 gainers of the day"
    re.compile(r"\btop\s+\d+\s+\w+", re.I),
    # "which stock has the highest yield?", "what should you buy?"
    re.compile(r"^\s*(?:which|what|whose|how)\b.*\?\s*$", re.I),
    re.compile(r"\b(?:highest|best|lowest)\s+(?:yield|return|growth)\b", re.I),
    # trailing enumeration: "Coal India, Wipro or ONGC?"
    re.compile(r"\b\w+\s*,\s*[\w ]+?\s+or\s+\w+\?", re.I),
    re.compile(r"\bstocks?\s+to\s+buy\b", re.I),
    re.compile(r"\bshould\s+you\s+buy\b", re.I),
    re.compile(r"\bmultibagger\b", re.I),
    re.compile(r"\bstocks?\s+to\s+watch\b", re.I),
    re.compile(r"\b\d+\s+stocks?\b.*\b(?:watch|focus|picks?|gainers|losers)\b", re.I),
    re.compile(r"\bmarket\s+(?:outlook|wrap|roundup|review)\b", re.I),
    # index wrap commentary - allow the plural verb forms
    re.compile(r"\b(?:sensex|nifty)\b.*\b(?:sheds?|gains?|rises?|falls?|drops?|jumps?)\b.*\bpoints\b", re.I),
    re.compile(r"\btarget,?\s+stop-?loss\b", re.I),
    re.compile(r"\bstocks?\s+in\s+focus\b", re.I),
    # explainers carry no new information
    re.compile(r"\bhere(?:'s| is)\s+(?:why|what|how)\b", re.I),
    re.compile(r"\b(?:explained|full\s+list)\b", re.I),
]


def looks_like_noise(title: str) -> Optional[str]:
    """Return the matched noise pattern, or ``None`` when the headline is fine."""
    if not title:
        return "empty headline"
    for pattern in _NOISE_PATTERNS:
        if pattern.search(title):
            return pattern.pattern
    return None

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_URL_IN_TEXT_RE = re.compile(r"https?://\S+")
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){9,13}")
_WS_RE = re.compile(r"\s+")


class RunStats:
    """Counters that make a run auditable from its log output alone."""

    def __init__(self) -> None:
        self.started_at = datetime.now(IST)
        self.sources_queried: List[str] = []
        self.articles_scraped = 0
        self.articles_fresh = 0
        self.articles_stale = 0
        self.articles_no_timestamp = 0
        self.articles_irrelevant = 0
        self.articles_noise = 0
        self.rejected_non_catalyst = 0
        self.rejected_non_directional = 0
        self.rejected_low_relevance = 0
        self.stories_clustered = 0
        self.stories_new = 0
        self.stories_duplicate = 0
        self.stories_development = 0
        self.candidates_ranked = 0
        self.ai_assessed = 0
        self.ai_failed = 0
        self.market_ok = 0
        self.market_unavailable = 0
        self.validated_ok = 0
        self.validated_rejected: List[str] = []
        self.sent = 0

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)

    def log_summary(self) -> None:
        logger.info("---- RUN SUMMARY ----")
        logger.info("started (IST)        : %s", self.started_at.strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("sources queried      : %d (%s)", len(self.sources_queried),
                    ", ".join(self.sources_queried[:6]) + ("..." if len(self.sources_queried) > 6 else ""))
        logger.info("articles scraped     : %d", self.articles_scraped)
        logger.info("  fresh              : %d", self.articles_fresh)
        logger.info("  stale              : %d", self.articles_stale)
        logger.info("  no timestamp       : %d", self.articles_no_timestamp)
        logger.info("  irrelevant         : %d", self.articles_irrelevant)
        logger.info("  opinion/listicle   : %d", self.articles_noise)
        logger.info("stories clustered    : %d", self.stories_clustered)
        logger.info("  new                : %d", self.stories_new)
        logger.info("  duplicate          : %d", self.stories_duplicate)
        logger.info("  new development    : %d", self.stories_development)
        logger.info("candidates ranked    : %d", self.candidates_ranked)
        logger.info("AI assessed          : %d (failed %d)", self.ai_assessed, self.ai_failed)
        logger.info("  low relevance      : %d", self.rejected_low_relevance)
        logger.info("  non-catalyst       : %d", self.rejected_non_catalyst)
        logger.info("  non-directional    : %d", self.rejected_non_directional)
        logger.info("market data ok       : %d", self.market_ok)
        logger.info("market unavailable   : %d", self.market_unavailable)
        logger.info("validated ok         : %d", self.validated_ok)
        logger.info("validation rejected : %d", len(self.validated_rejected))
        for reason in self.validated_rejected:
            logger.info("    - %s", reason)
        logger.info("sent to Telegram    : %d", self.sent)


# ---------------------------------------------------------------------------
# Freshness
# ---------------------------------------------------------------------------

def parse_published(raw: str) -> Optional[datetime]:
    """Parse a publisher timestamp into an aware IST datetime.

    Handles RFC 822 (RSS), ISO 8601 and a few common Indian formats. Returns
    ``None`` when the value cannot be trusted - and the caller then treats the
    article as *not fresh*, rather than assuming it is new.
    """
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None

    from email.utils import parsedate_to_datetime

    for parser in (parsedate_to_datetime,):
        try:
            value = parser(text)
            if value is not None:
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                return value.astimezone(IST)
        except (TypeError, ValueError, IndexError):
            pass

    cleaned = text.replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(cleaned)
        if value.tzinfo is None:
            value = value.replace(tzinfo=IST)
        return value.astimezone(IST)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S", "%d-%m-%Y", "%d %b %Y %H:%M:%S", "%d %b %Y",
        "%I:%M %p, %d %B %Y", "%B %d, %Y",
    ):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


@dataclass
class Candidate:
    """One de-duplicated story with its verified company attached."""

    title: str
    url: str
    canonical_url: str
    source: str
    tier: int
    published_at: Optional[datetime]
    content: str = ""
    summary: str = ""
    members: List[Dict[str, Any]] = field(default_factory=list)
    story_key: str = ""
    resolution: Optional[Resolution] = None
    is_development: bool = False
    prior_headline: str = ""

    @property
    def corroborating_sources(self) -> List[str]:
        return sorted({m.get("source", "") for m in self.members if m.get("source")})

    @property
    def corroborating_urls(self) -> List[str]:
        return sorted({m.get("url", "") for m in self.members if m.get("url")})

    def published_iso(self) -> str:
        return self.published_at.isoformat() if self.published_at else ""

    def to_article_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "source": self.source,
            "tier": self.tier,
            "content": self.content or self.summary,
            "summary": self.summary,
            "published_at": self.published_iso(),
            "corroborating_sources": self.corroborating_sources,
        }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class NewsSignalPipeline:
    """End-to-end: articles in, validated signals out."""

    def __init__(
        self,
        store: StoryStore,
        *,
        market: Optional[MarketDataClient] = None,
        resolver=None,
        ai: Optional[AIClient] = None,
        freshness_hours: int = DEFAULT_FRESHNESS_HOURS,
        max_signals: int = MAX_SIGNALS_PER_RUN,
        ticker_cooldown_hours: int = DEFAULT_TICKER_COOLDOWN_HOURS,
        validator: Optional[SignalValidator] = None,
        ticker_allowlist: Optional[set] = None,
        min_relevance: int = MIN_RELEVANCE_SCORE,
        non_catalyst_events: Optional[set] = None,
    ):
        self.store = store
        self.market = market or get_market_client()
        self.resolver = resolver or get_resolver()
        self.ai = ai or AIClient()
        self.freshness_hours = freshness_hours
        self.max_signals = max(1, min(max_signals, MAX_SIGNALS_PER_RUN))
        self.ticker_cooldown_hours = ticker_cooldown_hours
        self.validator = validator or SignalValidator()
        # When set, only these tickers may produce a signal (`scan` mode).
        self.ticker_allowlist = ticker_allowlist or None
        self.min_relevance = min_relevance
        self.non_catalyst_events = non_catalyst_events or NON_CATALYST_EVENT_TYPES
        self.stats = RunStats()

    # -- history ----------------------------------------------------------
    def _known_headlines(self) -> List[Tuple[str, str]]:
        """(key, headline) pairs from persistent history.

        Sent stories matter most, but everything recently *seen* matters too:
        re-analysing an article we already decided was noise is waste.
        """
        rows: List[Tuple[str, str]] = []
        try:
            for story in self.store.recent_signals(days=30, limit=300):
                if story.story_key:
                    rows.append((story.story_key, story.article_title))
            for article in self.store.recent_articles(hours=24 * 14, limit=800):
                if article.canonical_url:
                    rows.append((f"url:{article.canonical_url}", article.title))
                    if article.title_fp:
                        rows.append((f"title:{article.title_fp}", article.title))
        except Exception as exc:
            logger.warning("Could not load history for dedup: %s", exc)
        return rows

    def _sent_headlines(self) -> List[Tuple[str, str]]:
        """Headlines that have already produced a Telegram message.

        Tracked separately from ``_known_headlines`` because "we have seen this
        before" and "we already told the user" need different handling.
        """
        rows: List[Tuple[str, str]] = []
        try:
            sent_keys = self.store.sent_story_keys()
        except Exception as exc:
            logger.warning("Could not load sent stories: %s", exc)
            return rows

        try:
            for story in self.store.recent_signals(days=30, limit=300):
                if story.story_key in sent_keys and story.article_title:
                    rows.append((story.story_key, story.article_title))
        except Exception as exc:
            logger.warning("Could not load sent signal headlines: %s", exc)

        try:
            for article in self.store.recent_articles(hours=24 * 30, limit=800):
                if article.sent and article.title:
                    rows.append((article.story_key or article.canonical_url, article.title))
        except Exception as exc:
            logger.warning("Could not load sent articles: %s", exc)
        return rows

    # -- step 1: freshness + relevance -------------------------------------
    def _screen_articles(self, articles: Sequence[Any]) -> List[Candidate]:
        """Turn raw scraped items into candidates, before any LLM spend."""
        now = datetime.now(IST)
        cutoff = now - timedelta(hours=self.freshness_hours)
        candidates: List[Candidate] = []

        for raw in articles or []:
            item = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw or {})
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            self.stats.articles_scraped += 1

            if len(title) < 15:
                self.stats.articles_irrelevant += 1
                continue

            noise = looks_like_noise(title)
            if noise:
                # Opinion pieces and listicles are filtered before any LLM
                # spend: they are the majority of a market wrap and can never
                # justify a signal.
                self.stats.articles_noise += 1
                logger.info("Skipping (opinion/listicle): %s", title[:70])
                continue
            if not url or not url.startswith("http"):
                self.stats.articles_irrelevant += 1
                continue

            published_raw = item.get("published") or item.get("published_at") or ""
            published = parse_published(published_raw)

            if published is None:
                # No trustworthy timestamp: do not treat as new. Counted so the
                # run log shows exactly how much news was excluded for this.
                self.stats.articles_no_timestamp += 1
                logger.info("Skipping (no usable timestamp): %s", title[:70])
                continue
            if published > now + timedelta(hours=2):
                self.stats.articles_stale += 1
                logger.info("Skipping (future timestamp): %s", title[:70])
                continue
            if published < cutoff:
                self.stats.articles_stale += 1
                logger.info(
                    "Skipping (%.1fh old, window %dh): %s",
                    (now - published).total_seconds() / 3600.0,
                    self.freshness_hours, title[:70],
                )
                continue

            content = item.get("content") or item.get("summary") or ""
            if len(content) < MIN_ARTICLE_CHARS:
                # Keep it: the model can still work from a headline, and the
                # freshness test above is the important one.
                logger.debug("Thin article body: %s", title[:60])

            candidates.append(Candidate(
                title=title,
                url=url,
                canonical_url=canonical_url(url),
                source=item.get("source", "unknown"),
                tier=int(item.get("tier", 3) or 3),
                published_at=published,
                content=content,
                summary=item.get("summary", "") or "",
                members=[item],
            ))
            self.stats.articles_fresh += 1

        return candidates

    # -- step 2: cross-source clustering ----------------------------------
    def _cluster(self, candidates: Sequence[Candidate]) -> List[Candidate]:
        """Merge same-event coverage into one candidate.

        The highest-tier outlet wins as the headline source, because a PIB or
        exchange filing outranks an aggregator rewrite.
        """
        clusters: List[List[Candidate]] = []
        for candidate in candidates:
            placed = False
            for cluster in clusters:
                head = cluster[0]
                if candidate.canonical_url and candidate.canonical_url == head.canonical_url:
                    cluster.append(candidate)
                    placed = True
                    break
                if title_similarity(candidate.title, head.title) >= 0.62:
                    cluster.append(candidate)
                    placed = True
                    break
            if not placed:
                clusters.append([candidate])

        merged: List[Candidate] = []
        for cluster in clusters:
            cluster.sort(key=lambda c: (c.tier, c.published_at or datetime.min.replace(tzinfo=IST)))
            primary = cluster[0]
            primary.members = [c.to_article_dict() for c in cluster]
            primary.corroborating_urls_extended = [  # type: ignore[attr-defined]
                u for c in cluster for u in [c.url]
            ]
            if len(cluster) > 1:
                logger.info(
                    "Clustered %d outlets into one story: %s",
                    len(cluster), primary.title[:70],
                )
            merged.append(primary)

        self.stats.stories_clustered = len(merged)
        return merged

    # -- step 3: cross-run dedup + developing stories ---------------------
    def _already_delivered(self, candidate: Candidate, sent_rows: List[Tuple[str, str]]) -> bool:
        """Has this story already been put in front of the user?

        Checked against headlines of *sent* stories only. A new development is
        allowed through by the caller before this matters - that is the whole
        point of tracking developments.
        """
        try:
            existing = self.store.get_article(candidate.canonical_url)
            if existing and existing.sent:
                return True
        except Exception:
            pass

        if not sent_rows:
            return False
        match = same_story(candidate.title, candidate.url, sent_rows)
        return bool(match.is_duplicate)

    def _apply_history(self, candidates: Sequence[Candidate]) -> List[Candidate]:
        known = self._known_headlines()
        sent_rows = self._sent_headlines()
        sent_keys = set()
        try:
            sent_keys = self.store.sent_story_keys()
        except Exception:
            pass
        kept: List[Candidate] = []

        for candidate in candidates:
            candidate.story_key = story_key_for(candidate.title, candidate.url)
            match = same_story(candidate.title, candidate.url, known)

            # A new development is *not* a repeat, even though it was matched
            # against a story we already covered. Decide this before the
            # already-delivered check, which would otherwise veto it.
            if match.is_new_development:
                candidate.is_development = True
                candidate.prior_headline = next(
                    (h for k, h in known if k == match.matched_key), ""
                )
                self.stats.stories_development += 1
                logger.info(
                    "NEW DEVELOPMENT of a known story: %s (follows: %s)",
                    candidate.title[:70], candidate.prior_headline[:50],
                )
                self.stats.stories_new += 1
                kept.append(candidate)
                continue

            if candidate.story_key in sent_keys or self._already_delivered(candidate, sent_rows):
                self.stats.stories_duplicate += 1
                logger.info(
                    "SUPPRESSED (already delivered): %s [%s]",
                    candidate.title[:70], match.reason,
                )
                continue

            self.stats.stories_new += 1
            kept.append(candidate)

        return kept

    # -- step 4: resolve verified Indian companies ------------------------
    def _resolve_companies(self, candidate: Candidate) -> Optional[Resolution]:
        haystack = f"{candidate.title} {candidate.content[:1500]} {candidate.summary}"
        resolutions = self.resolver.resolve_from_text(haystack)
        if not resolutions:
            return None
        # Prefer the largest verified listing when a story names several.
        best = None
        for resolution in resolutions:
            if resolution.verified:
                quote = self.market.get_quote(resolution.ticker)
                cap = quote.market_cap_cr if quote else 0.0
                if best is None or cap > best[0]:
                    best = (cap, resolution)
        if best:
            return best[1]
        return None

    # -- step 5: market context (real numbers, fetched before AI) ---------
    def _market_context(self, ticker: str) -> Optional[Dict[str, Any]]:
        snapshot = self.market.get_market_snapshot(ticker)
        if not snapshot:
            return None
        indicators = snapshot["indicators"]
        return {
            "quote": snapshot["quote"],
            "indicators": indicators,
            "session": snapshot["session"],
            "trend": trend_bias(indicators),
        }

    # -- step 6: AI assessment (labels + prose only) ----------------------
    def _assess(self, candidate: Candidate, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        quote = context["quote"]
        indicators = context["indicators"]
        market_for_prompt = {
            "price": quote.price,
            "price_kind": quote.price_kind,
            "trend": context["trend"],
            "rsi_14": indicators.rsi_14,
            "sma_20": indicators.sma_20,
        }
        prompt = interpret.build_assessment_prompt(
            candidate.to_article_dict(),
            candidates=[{
                "company_name": context["resolution"].company_name,
                "ticker": context["resolution"].ticker,
                "exchange": quote.exchange,
                "sector": "unknown",
            }],
            market_context=market_for_prompt,
        )
        result = self.ai.ask_json(interpret.SYSTEM, prompt, max_tokens=1200)
        if result is None:
            return None

        if not result.get("is_material", False):
            logger.info(
                "AI: not material (%s) - %s",
                result.get("rejection_reason", "no reason given"),
                candidate.title[:60],
            )
            return None
        score = result.get("relevance_score", 0)
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 0
        if score < self.min_relevance:
            self.stats.rejected_low_relevance += 1
            logger.info(
                "AI: relevance %s below the %s floor - %s",
                score, self.min_relevance, candidate.title[:60],
            )
            return None

        event_type = str(result.get("event_type", "OTHER")).upper()
        if event_type in self.non_catalyst_events:
            self.stats.rejected_non_catalyst += 1
            logger.info(
                "AI: %s is commentary, not a company catalyst - %s",
                event_type, candidate.title[:60],
            )
            return None

        result["relevance_score"] = score
        result["event_type"] = event_type
        return result

    # -- step 7: assemble + validate --------------------------------------
    def _build_signal(
        self,
        candidate: Candidate,
        context: Dict[str, Any],
        assessment: Dict[str, Any],
        levels,
    ) -> Dict[str, Any]:
        quote = context["quote"]
        indicators = context["indicators"]
        resolution = context["resolution"]

        levels_summary = (
            f"entry {levels.entry} | target {levels.target} | stop {levels.stop} | "
            f"risk/reward {levels.risk_reward} | risk {levels.risk_pct}% | "
            f"reward {levels.reward_pct}%"
        )
        technicals_summary = "; ".join(describe_technicals(indicators))
        narrative = self.ai.ask_json(
            interpret.SYSTEM,
            interpret.build_signal_narrative_prompt(
                company_name=resolution.company_name or quote.company_name,
                ticker=resolution.ticker,
                event_summary=assessment.get("catalyst_summary", ""),
                why_it_matters=assessment.get("why_it_matters", ""),
                key_risk=assessment.get("key_risk", ""),
                levels_summary=levels_summary,
                technicals_summary=technicals_summary,
            ),
            max_tokens=600,
        ) or {}

        return {
            "ticker": resolution.ticker,
            "exchange": quote.exchange,
            "company_name": resolution.company_name or quote.company_name,
            "direction": (assessment.get("direction") or "LONG").upper(),
            "event_type": assessment.get("event_type", "OTHER"),
            "relevance_score": assessment.get("relevance_score", 0),
            "article": {
                **candidate.to_article_dict(),
                "is_development": candidate.is_development,
                "prior_headline": candidate.prior_headline,
            },
            "facts": {
                "price": quote.price,
                "price_kind": quote.price_kind,
                "price_asof": quote.as_of,
                "price_source": quote.source,
                "prev_close": quote.prev_close,
                "change_pct": quote.change_pct,
                "volume": quote.volume,
                "market_cap_cr": quote.market_cap_cr,
                "session": context["session"].session,
                "session_label": quote.session_label,
            },
            "calculated": {
                **levels.as_dict(),
                "trend": context["trend"],
                "rsi_14": indicators.rsi_14,
                "sma_20": indicators.sma_20,
                "sma_50": indicators.sma_50,
                "atr_14": indicators.atr_14,
                "support_20": indicators.support_20,
                "resistance_20": indicators.resistance_20,
                "volatility": volatility_score(indicators),
            },
            "ai": {
                "thesis": narrative.get("thesis") or assessment.get("why_it_matters", ""),
                "risk": assessment.get("key_risk", ""),
                "catalyst": assessment.get("catalyst_summary", ""),
                "watchpoint": narrative.get("watchpoint", ""),
                "evidence": narrative.get("evidence", ""),
                "event_type": assessment.get("event_type", "OTHER"),
                "time_horizon_days": assessment.get("time_horizon_days"),
            },
            "levels": levels,
            "quote": quote,
            "indicators": indicators,
            "resolution": resolution,
        }

    def _in_cooldown(self, ticker: str) -> bool:
        """Has this ticker already been *delivered* recently?

        Only signals flagged ``sent`` count. A signal that was analysed and
        persisted but never delivered - because Telegram was down, say - must
        not block that ticker for the next 48 hours; the user never saw it.
        """
        try:
            recent = self.store.recent_signals_for_ticker(ticker, hours=self.ticker_cooldown_hours)
        except Exception as exc:
            logger.warning("Cooldown lookup failed for %s: %s", ticker, exc)
            return False
        return any(getattr(s, "sent", 0) for s in recent)

    # -- orchestration -----------------------------------------------------
    def run(self, articles: Sequence[Any]) -> List[Dict[str, Any]]:
        """Produce at most ``max_signals`` validated signals."""
        logger.info(
            "Pipeline start: max_signals=%d freshness=%dh cooldown=%dh store=%s",
            self.max_signals, self.freshness_hours, self.ticker_cooldown_hours,
            self.store.name,
        )
        session = market_status()
        logger.info("Market session: %s (%s)", session.session, session.label)

        try:
            from src.scraping.scraper import SOURCES as _SOURCES
            self.stats.sources_queried = [src.get("name", "?") for src in _SOURCES]
        except Exception:
            pass

        fresh = self._screen_articles(articles)
        if not fresh:
            logger.info("No fresh articles survived the freshness screen")
            self.stats.log_summary()
            return []

        clustered = self._cluster(fresh)
        candidates = self._apply_history(clustered)
        if not candidates:
            logger.info("All clustered stories were already sent")
            self.stats.log_summary()
            return []

        # Highest tier, then most recent, then AI relevance is applied later.
        candidates.sort(
            key=lambda c: (c.tier, -(c.published_at.timestamp() if c.published_at else 0))
        )

        signals: List[Dict[str, Any]] = []
        seen_tickers: set = set()

        for candidate in candidates:
            if len(signals) >= self.max_signals:
                logger.info("Reached the %d-signal ceiling; stopping", self.max_signals)
                break

            resolution = self._resolve_companies(candidate)
            if resolution is None:
                logger.info("No verified Indian company in: %s", candidate.title[:70])
                continue
            if resolution.ticker in seen_tickers:
                continue
            if self.ticker_allowlist and resolution.ticker not in self.ticker_allowlist:
                logger.info(
                    "Screener filter: %s is not currently flagged, skipping",
                    resolution.ticker,
                )
                continue
            # A ticker delivered recently is *deprioritised*, never blocked.
            # Repeats are already suppressed at story level, so a hard
            # per-ticker mute would only ever discard genuinely new material
            # news - the case the product explicitly requires us to allow.
            recently_sent = self._in_cooldown(resolution.ticker)
            if recently_sent:
                logger.info(
                    "%s was delivered within %dh - deprioritising, not blocking",
                    resolution.ticker, self.ticker_cooldown_hours,
                )

            self.stats.candidates_ranked += 1
            context = self._market_context(resolution.ticker)
            if context is None:
                self.stats.market_unavailable += 1
                logger.warning(
                    "MARKET DATA UNAVAILABLE for %s - signal skipped, no price invented",
                    resolution.ticker,
                )
                continue
            self.stats.market_ok += 1
            context["resolution"] = resolution

            self.stats.ai_assessed += 1
            assessment = self._assess(candidate, context)
            if assessment is None:
                # Usually a free-tier rate limit that survived the provider
                # fallback chain. Recorded so the run log explains itself.
                self.stats.ai_failed += 1
                logger.warning(
                    "AI produced no usable assessment for %s (%s) - not sending",
                    resolution.ticker, getattr(self.ai, "last_error", "no reason recorded"),
                )
                continue

            direction = (assessment.get("direction") or "NEUTRAL").upper()
            if direction not in ("LONG", "SHORT"):
                # The model judged this material but not directional. There is
                # no trade to express, so it is reported as nothing rather
                # than coerced into a LONG we do not believe.
                self.stats.rejected_non_directional += 1
                logger.info(
                    "AI: direction NEUTRAL - material but not actionable, skipping %s",
                    resolution.ticker,
                )
                continue
            levels = derive_levels(context["indicators"], direction)

            signal = self._build_signal(candidate, context, assessment, levels)

            verdict = self.validator.validate(
                signal=signal,
                article=signal["article"],
                quote=context["quote"],
                indicators=context["indicators"],
                levels=levels,
                resolution=resolution,
                store=self.store,
                freshness_window_hours=self.freshness_hours,
            )
            if not verdict.ok:
                self.stats.validated_rejected.append(
                    f"{resolution.ticker}: {'; '.join(verdict.reasons)}"
                )
                continue

            self.stats.validated_ok += 1
            seen_tickers.add(resolution.ticker)
            signal["_recently_sent"] = recently_sent
            signals.append(signal)

        # Ranking, in order of what actually matters:
        #   1. a ticker we have not just messaged about, so three slots are not
        #      filled with three stories about one company
        #   2. the model's own relevance score
        #   3. the risk/reward our own maths produced
        signals.sort(
            key=lambda s: (
                not s.get("_recently_sent", False),
                s.get("relevance_score", 0),
                s["calculated"].get("risk_reward", 0),
            ),
            reverse=True,
        )
        signals = signals[: self.max_signals]
        self.stats.log_summary()
        return signals

    # -- persistence -------------------------------------------------------
    def persist(self, signals: Sequence[Dict[str, Any]]) -> int:
        """Write article, story and signal rows. Never raises."""
        now = utcnow().isoformat()
        articles: List[ArticleRecord] = []
        stories: List[StoryRecord] = []
        records: List[SignalRecord] = []

        for index, signal in enumerate(signals):
            article = signal["article"]
            quote = signal["quote"]
            indicators = signal["indicators"]
            levels = signal["levels"]
            calculated = signal["calculated"]
            facts = signal["facts"]
            ai = signal["ai"]
            resolution = signal["resolution"]
            candidate_key = signal.get("story_key") or story_key_for(
                article["title"], article["canonical_url"]
            )
            signal_id = f"{resolution.ticker}_{now.replace(':', '').replace('-', '')}_{index}"

            articles.append(ArticleRecord(
                canonical_url=article["canonical_url"],
                url=article["url"],
                source=article["source"],
                tier=int(article.get("tier", 3) or 3),
                title=article["title"],
                norm_title="",
                title_fp=title_fingerprint(article["title"]),
                content_fp=content_fingerprint(article.get("content", "")),
                published_at=article.get("published_at", ""),
                first_seen_at=now,
                processed_at=now,
                sent=0,
                status="processed",
                tickers=[resolution.ticker],
                story_key=candidate_key,
                metadata={
                    "corroborating_sources": article.get("corroborating_sources", []),
                    "is_development": article.get("is_development", False),
                },
            ))

            stories.append(StoryRecord(
                story_key=candidate_key,
                canonical_headline=article["title"],
                norm_headline="",
                first_seen_at=now,
                last_seen_at=now,
                sent_count=0,
                status="processed",
                tickers=[resolution.ticker],
                sources=article.get("corroborating_sources", []) or [article["source"]],
                article_urls=[article["canonical_url"]],
                development_index=1 if article.get("is_development") else 0,
                metadata={"event_type": ai.get("event_type", "")},
            ))

            signal["_signal_id"] = signal_id
            records.append(SignalRecord(
                signal_id=signal_id,
                story_key=candidate_key,
                article_canonical_url=article["canonical_url"],
                article_title=article["title"],
                source=article["source"],
                ticker=resolution.ticker,
                exchange=quote.exchange,
                company_name=resolution.company_name or quote.company_name,
                direction=levels.direction,
                generated_at=now,
                market_price=quote.price,
                market_price_asof=quote.as_of,
                market_price_source=quote.source,
                prev_close=quote.prev_close,
                day_change_pct=quote.change_pct or 0.0,
                volume=quote.volume,
                session=facts.get("session", ""),
                entry=levels.entry,
                target=levels.target,
                stop=levels.stop,
                risk_reward=levels.risk_reward,
                rsi_14=indicators.rsi_14 or 0.0,
                sma_20=indicators.sma_20 or 0.0,
                sma_50=indicators.sma_50 or 0.0,
                atr_14=indicators.atr_14 or 0.0,
                support=indicators.support_20 or 0.0,
                resistance=indicators.resistance_20 or 0.0,
                levels_strategy=levels.strategy,
                calculation_meta=calculated.get("basis", {}),
                ai_confidence=int(ai.get("relevance_score", 0) or 0),
                ai_thesis=ai.get("thesis", ""),
                ai_risk=ai.get("risk", ""),
                ai_catalyst=ai.get("catalyst", ""),
                ai_watchpoints=ai.get("watchpoint", ""),
                ai_evidence=ai.get("evidence", ""),
                relevance_score=float(ai.get("relevance_score", 0) or 0),
                sent=0,
                metadata={"event_type": ai.get("event_type", "")},
            ))

        written = 0
        try:
            self.store.upsert_articles(articles)
            self.store.upsert_stories(stories)
            written = self.store.record_signals(records)
            self.store.flush()
            logger.info("Persisted %d signal(s) to %s store", written, self.store.name)
        except Exception as exc:
            logger.error("Persistence failed (signals still deliverable): %s", exc)
        return written

    def mark_sent(self, signals: Sequence[Dict[str, Any]]) -> None:
        """Flag rows as delivered so they are never sent again.

        Must update the *signal* row as well as the article and story rows:
        the per-ticker cooldown reads ``SignalRecord.sent``, so leaving it
        unset would silently disable the cooldown.
        """
        for signal in signals:
            signal_id = signal.get("_signal_id")
            if signal_id:
                try:
                    self.store.mark_signal_sent(signal_id)
                except Exception as exc:
                    logger.error("Could not mark signal %s sent: %s", signal_id, exc)

            article = signal["article"]
            try:
                self.store.upsert_articles([ArticleRecord(
                    canonical_url=article["canonical_url"],
                    url=article["url"],
                    source=article["source"],
                    title=article["title"],
                    title_fp=title_fingerprint(article["title"]),
                    first_seen_at=utcnow().isoformat(),
                    sent=1,
                    status="sent",
                    tickers=[signal["ticker"]],
                    story_key=story_key_for(article["title"], article["canonical_url"]),
                )])
            except Exception as exc:
                logger.error("Could not mark article sent: %s", exc)

            try:
                self.store.upsert_stories([StoryRecord(
                    story_key=story_key_for(article["title"], article["canonical_url"]),
                    canonical_headline=article["title"],
                    first_seen_at=utcnow().isoformat(),
                    last_seen_at=utcnow().isoformat(),
                    first_sent_at=utcnow().isoformat(),
                    sent_count=1,
                    status="sent",
                    tickers=[signal["ticker"]],
                    sources=article.get("corroborating_sources", []) or [article["source"]],
                    article_urls=[article["canonical_url"]],
                )])
            except Exception as exc:
                logger.error("Could not mark story sent: %s", exc)

        try:
            self.store.flush()
        except Exception as exc:
            logger.error("Store flush after send failed: %s", exc)
