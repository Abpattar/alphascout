"""Persistent state for AlphaScout.

Why this module exists
----------------------
AlphaScout runs on ephemeral GitHub Actions runners: whatever is written to
``data/`` is destroyed when the job ends. Before this module, the SQLite
database that held article history, sent signals and outcome records was
therefore empty at the start of every run, which silently disabled
deduplication, the per-ticker cooldown, and confidence calibration.

``StoryStore`` is the single persistence seam. Two backends implement it:

* :class:`GitStateStore` - writes compact JSONL under ``state/`` and commits
  it back to the repository. Free, no external account, works today.
* :class:`SupabaseStore` - PostgreSQL via Supabase. Same interface, selected
  by environment variable.

The active backend is chosen once in :func:`get_store`. There is exactly one
production code path; the backend is an implementation detail.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30), "IST")

# How long we keep per-article rows. Stories/signals are kept longer because
# they are far fewer and are what dedup actually consults.
ARTICLE_RETENTION_DAYS = 120
STORY_RETENTION_DAYS = 365
SIGNAL_RETENTION_DAYS = 365


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

@dataclass
class ArticleRecord:
    """One article we have seen, whether or not it was ever sent."""

    canonical_url: str
    url: str = ""
    source: str = ""
    tier: int = 3
    title: str = ""
    norm_title: str = ""
    title_fp: str = ""
    content_fp: str = ""
    published_at: str = ""       # from the publisher, normalised to UTC ISO
    first_seen_at: str = ""     # when we first scraped it
    processed_at: str = ""      # when the LLM pipeline last examined it
    sent: int = 0               # 1 if this article produced a Telegram message
    status: str = "seen"        # seen | processed | rejected | sent | duplicate
    tickers: List[str] = field(default_factory=list)
    story_key: str = ""
    rejection_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ArticleRecord":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class StoryRecord:
    """A de-duplicated event, possibly reported by several outlets."""

    story_key: str
    canonical_headline: str = ""
    norm_headline: str = ""
    first_seen_at: str = ""
    last_seen_at: str = ""
    first_sent_at: str = ""
    sent_count: int = 0
    status: str = "seen"        # seen | sent | suppressed
    tickers: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    article_urls: List[str] = field(default_factory=list)
    development_index: int = 0  # how many distinct developments seen
    last_development_fp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StoryRecord":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class SignalRecord:
    """A validated trade signal. Every numeric field is market-derived."""

    signal_id: str
    story_key: str = ""
    article_canonical_url: str = ""
    article_title: str = ""
    source: str = ""
    ticker: str = ""
    exchange: str = ""
    company_name: str = ""
    direction: str = "LONG"
    generated_at: str = ""

    # --- FACTUAL market data (source: market data provider) ---
    market_price: float = 0.0
    market_price_asof: str = ""
    market_price_source: str = ""
    prev_close: float = 0.0
    day_change_pct: float = 0.0
    volume: float = 0.0
    session: str = ""           # OPEN | CLOSED | PRE_OPEN | WEEKEND | HOLIDAY

    # --- CALCULATED (deterministic code) ---
    entry: float = 0.0
    target: float = 0.0
    stop: float = 0.0
    risk_reward: float = 0.0
    rsi_14: float = 0.0
    sma_20: float = 0.0
    sma_50: float = 0.0
    atr_14: float = 0.0
    support: float = 0.0
    resistance: float = 0.0
    levels_strategy: str = ""
    calculation_meta: Dict[str, Any] = field(default_factory=dict)

    # --- AI INTERPRETATION (never numeric market facts) ---
    ai_confidence: int = 0
    ai_thesis: str = ""
    ai_risk: str = ""
    ai_catalyst: str = ""
    ai_watchpoints: str = ""
    ai_evidence: str = ""
    relevance_score: float = 0.0

    sent: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SignalRecord":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class StoryStore(ABC):
    """Everything AlphaScout needs to remember between runs."""

    name = "abstract"

    @abstractmethod
    def health_check(self) -> Tuple[bool, str]:
        """Verify the backend is reachable. Never raises."""

    @abstractmethod
    def upsert_articles(self, records: Iterable[ArticleRecord]) -> int:
        """Insert or merge article rows. Returns number written."""

    @abstractmethod
    def get_article(self, canonical_url: str) -> Optional[ArticleRecord]:
        ...

    @abstractmethod
    def upsert_stories(self, records: Iterable[StoryRecord]) -> int:
        ...

    @abstractmethod
    def get_story(self, story_key: str) -> Optional[StoryRecord]:
        ...

    @abstractmethod
    def record_signals(self, records: Iterable[SignalRecord]) -> int:
        ...

    @abstractmethod
    def mark_signal_sent(self, signal_id: str) -> bool:
        ...

    @abstractmethod
    def sent_story_keys(self) -> set:
        """Story keys that have already produced a Telegram message."""

    @abstractmethod
    def recent_articles(self, hours: int = 48, limit: int = 500) -> List[ArticleRecord]:
        ...

    @abstractmethod
    def recent_signals(self, days: int = 30, limit: int = 200) -> List[SignalRecord]:
        ...

    @abstractmethod
    def recent_signals_for_ticker(self, ticker: str, hours: int = 48) -> List[SignalRecord]:
        ...

    @abstractmethod
    def counts(self) -> Dict[str, int]:
        ...

    @abstractmethod
    def flush(self) -> None:
        """Commit pending writes. Must be safe to call more than once."""


# ---------------------------------------------------------------------------
# Git-backed store
# ---------------------------------------------------------------------------

class GitStateStore(StoryStore):
    """Durable state stored as JSONL committed back to the repository.

    Chosen when no external database is configured. The payload is small
    (fingerprints and numbers, never article bodies) and compaction keeps it
    bounded: rows outside the retention window are dropped on every flush.
    """

    name = "git-state"

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2]
        self.dir = self.root / "state"
        self._lock = threading.RLock()
        self._articles: Dict[str, ArticleRecord] = {}
        self._stories: Dict[str, StoryRecord] = {}
        self._signals: Dict[str, SignalRecord] = {}
        self._dirty = False
        self._load()

    # -- files -------------------------------------------------------------
    def _path(self, name: str) -> Path:
        return self.dir / name

    def _read_jsonl(self, name: str) -> List[Dict[str, Any]]:
        path = self._path(name)
        if not path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping corrupt row in %s", name)
        except OSError as exc:
            logger.warning("Could not read %s: %s", path, exc)
        return rows

    def _load(self) -> None:
        with self._lock:
            for row in self._read_jsonl("articles.jsonl"):
                rec = ArticleRecord.from_dict(row)
                self._articles[rec.canonical_url] = rec
            for row in self._read_jsonl("stories.jsonl"):
                rec = StoryRecord.from_dict(row)
                self._stories[rec.story_key] = rec
            for row in self._read_jsonl("signals.jsonl"):
                rec = SignalRecord.from_dict(row)
                self._signals[rec.signal_id] = rec
            logger.info(
                "GitStateStore loaded: %d articles, %d stories, %d signals",
                len(self._articles), len(self._stories), len(self._signals),
            )

    def _write_jsonl(self, name: str, records: Iterable[Any]) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for rec in records:
                handle.write(rec.to_json() + "\n")
        tmp.replace(path)

    @staticmethod
    def _prune(records: Iterable[Any], field_name: str, days: int) -> List[Any]:
        cutoff = utcnow() - timedelta(days=days)
        kept = []
        for rec in records:
            raw = getattr(rec, field_name, "") or ""
            try:
                when = datetime.fromisoformat(raw) if raw else None
            except ValueError:
                when = None
            if when is None or when >= cutoff:
                kept.append(rec)
        return kept

    # -- interface ---------------------------------------------------------
    def health_check(self) -> Tuple[bool, str]:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            probe = self.dir / ".health"
            probe.write_text(iso(utcnow()), encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True, f"writable: {self.dir}"
        except Exception as exc:
            return False, f"not writable: {exc}"

    def upsert_articles(self, records: Iterable[ArticleRecord]) -> int:
        written = 0
        with self._lock:
            for rec in records:
                if not rec.canonical_url:
                    continue
                existing = self._articles.get(rec.canonical_url)
                if existing is None:
                    self._articles[rec.canonical_url] = rec
                    written += 1
                else:
                    # Never downgrade a sent row back to seen.
                    existing.sent = existing.sent or rec.sent
                    existing.tickers = sorted(set(existing.tickers) | set(rec.tickers))
                    existing.story_key = existing.story_key or rec.story_key
                    existing.metadata.update(rec.metadata)
                    if rec.status != "seen":
                        existing.status = rec.status
                    if rec.processed_at:
                        existing.processed_at = rec.processed_at
                    if rec.rejection_reason:
                        existing.rejection_reason = rec.rejection_reason
                    written += 1
            self._dirty = True
        return written

    def get_article(self, canonical_url: str) -> Optional[ArticleRecord]:
        with self._lock:
            return self._articles.get(canonical_url)

    def upsert_stories(self, records: Iterable[StoryRecord]) -> int:
        written = 0
        with self._lock:
            for rec in records:
                if not rec.story_key:
                    continue
                existing = self._stories.get(rec.story_key)
                if existing is None:
                    self._stories[rec.story_key] = rec
                else:
                    existing.last_seen_at = rec.last_seen_at or existing.last_seen_at
                    existing.sent_count = max(existing.sent_count, rec.sent_count)
                    existing.first_sent_at = existing.first_sent_at or rec.first_sent_at
                    existing.tickers = sorted(set(existing.tickers) | set(rec.tickers))
                    existing.sources = sorted(set(existing.sources) | set(rec.sources))
                    existing.article_urls = sorted(
                        set(existing.article_urls) | set(rec.article_urls)
                    )[:20]
                    existing.development_index = max(
                        existing.development_index, rec.development_index
                    )
                    existing.metadata.update(rec.metadata)
                    if rec.status != "seen":
                        existing.status = rec.status
                written += 1
            self._dirty = True
        return written

    def get_story(self, story_key: str) -> Optional[StoryRecord]:
        with self._lock:
            return self._stories.get(story_key)

    def record_signals(self, records: Iterable[SignalRecord]) -> int:
        written = 0
        with self._lock:
            for rec in records:
                self._signals[rec.signal_id] = rec
                written += 1
            self._dirty = True
        return written

    def mark_signal_sent(self, signal_id: str) -> bool:
        with self._lock:
            rec = self._signals.get(signal_id)
            if rec is None:
                return False
            rec.sent = 1
            self._dirty = True
            return True

    def sent_story_keys(self) -> set:
        with self._lock:
            return {k for k, v in self._stories.items() if v.sent_count > 0}

    def recent_articles(self, hours: int = 48, limit: int = 500) -> List[ArticleRecord]:
        cutoff = utcnow() - timedelta(hours=hours)
        out = []
        with self._lock:
            for rec in self._articles.values():
                raw = rec.first_seen_at or ""
                try:
                    when = datetime.fromisoformat(raw) if raw else None
                except ValueError:
                    when = None
                if when is None or when >= cutoff:
                    out.append(rec)
        out.sort(key=lambda r: r.first_seen_at or "", reverse=True)
        return out[:limit]

    def recent_signals(self, days: int = 30, limit: int = 200) -> List[SignalRecord]:
        cutoff = utcnow() - timedelta(days=days)
        out = []
        with self._lock:
            for rec in self._signals.values():
                raw = rec.generated_at or ""
                try:
                    when = datetime.fromisoformat(raw) if raw else None
                except ValueError:
                    when = None
                if when is None or when >= cutoff:
                    out.append(rec)
        out.sort(key=lambda r: r.generated_at or "", reverse=True)
        return out[:limit]

    def recent_signals_for_ticker(self, ticker: str, hours: int = 48) -> List[SignalRecord]:
        cutoff = utcnow() - timedelta(hours=hours)
        out = []
        for rec in self.recent_signals(days=max(2, hours // 24 + 1), limit=1000):
            if rec.ticker != ticker:
                continue
            raw = rec.generated_at or ""
            try:
                when = datetime.fromisoformat(raw) if raw else None
            except ValueError:
                continue
            if when is None or (utcnow() - when) < timedelta(hours=hours):
                out.append(rec)
        return out

    def counts(self) -> Dict[str, int]:
        with self._lock:
            return {
                "articles": len(self._articles),
                "stories": len(self._stories),
                "signals": len(self._signals),
                "sent_signals": sum(1 for s in self._signals.values() if s.sent),
            }

    def flush(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            self._write_jsonl(
                "articles.jsonl",
                self._prune(self._articles.values(), "first_seen_at", ARTICLE_RETENTION_DAYS),
            )
            self._write_jsonl(
                "stories.jsonl",
                self._prune(self._stories.values(), "last_seen_at", STORY_RETENTION_DAYS),
            )
            self._write_jsonl(
                "signals.jsonl",
                self._prune(self._signals.values(), "generated_at", SIGNAL_RETENTION_DAYS),
            )
            self._dirty = False
            logger.info("GitStateStore flushed to %s", self.dir)


# ---------------------------------------------------------------------------
# Supabase-backed store
# ---------------------------------------------------------------------------

_SUPABASE_SCHEMA = """
create table if not exists articles (
    canonical_url   text primary key,
    url             text not null default '',
    source          text not null default '',
    tier            int  not null default 3,
    title           text not null default '',
    norm_title      text not null default '',
    title_fp        text not null default '',
    content_fp      text not null default '',
    published_at    timestamptz,
    first_seen_at   timestamptz not null default now(),
    processed_at    timestamptz,
    sent            int  not null default 0,
    status          text not null default 'seen',
    tickers         jsonb not null default '[]'::jsonb,
    story_key       text not null default '',
    rejection_reason text not null default '',
    metadata        jsonb not null default '{{}}'::jsonb
);
create index if not exists idx_articles_first_seen on articles (first_seen_at desc);
create index if not exists idx_articles_story on articles (story_key);
create index if not exists idx_articles_sent on articles (sent);

create table if not exists stories (
    story_key         text primary key,
    canonical_headline text not null default '',
    norm_headline     text not null default '',
    first_seen_at     timestamptz not null default now(),
    last_seen_at      timestamptz not null default now(),
    first_sent_at     timestamptz,
    sent_count        int  not null default 0,
    status            text not null default 'seen',
    tickers           jsonb not null default '[]'::jsonb,
    sources           jsonb not null default '[]'::jsonb,
    article_urls      jsonb not null default '[]'::jsonb,
    development_index int  not null default 0,
    last_development_fp text not null default '',
    metadata          jsonb not null default '{{}}'::jsonb
);
create index if not exists idx_stories_sent on stories (sent_count);

create table if not exists signals (
    signal_id   text primary key,
    story_key   text not null default '',
    article_canonical_url text not null default '',
    article_title text not null default '',
    source     text not null default '',
    ticker     text not null,
    exchange   text not null default '',
    company_name text not null default '',
    direction  text not null default 'LONG',
    generated_at timestamptz not null default now(),

    market_price numeric not null default 0,
    market_price_asof timestamptz,
    market_price_source text not null default '',
    prev_close  numeric not null default 0,
    day_change_pct numeric not null default 0,
    volume      numeric not null default 0,
    session     text not null default '',

    entry numeric not null default 0,
    target numeric not null default 0,
    stop numeric not null default 0,
    risk_reward numeric not null default 0,
    rsi_14 numeric not null default 0,
    sma_20 numeric not null default 0,
    sma_50 numeric not null default 0,
    atr_14 numeric not null default 0,
    support numeric not null default 0,
    resistance numeric not null default 0,
    levels_strategy text not null default '',
    calculation_meta jsonb not null default '{{}}'::jsonb,

    ai_confidence int not null default 0,
    ai_thesis text not null default '',
    ai_risk text not null default '',
    ai_catalyst text not null default '',
    ai_watchpoints text not null default '',
    ai_evidence text not null default '',
    relevance_score numeric not null default 0,

    sent int not null default 0,
    metadata jsonb not null default '{{}}'::jsonb
);
create index if not exists idx_signals_ticker on signals (ticker, generated_at desc);
create index if not exists idx_signals_generated on signals (generated_at desc);
"""


class SupabaseStore(StoryStore):
    """PostgreSQL-backed store (Supabase free tier or any reachable Postgres).

    Requires ``SUPABASE_URL`` and ``SUPABASE_KEY`` (service-role key) or
    ``SUPABASE_DB_URL``. Uses the PostgREST HTTP endpoint so no database
    driver is needed - the SDK is an optional extra, and plain ``requests``
    is used when it is absent.
    """

    name = "supabase"

    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key
        self._articles: Dict[str, ArticleRecord] = {}
        self._stories: Dict[str, StoryRecord] = {}
        self._signals: Dict[str, SignalRecord] = {}
        self._pending_articles: List[ArticleRecord] = []
        self._pending_stories: List[StoryRecord] = []
        self._pending_signals: List[SignalRecord] = []
        self._session = None

    # -- transport ---------------------------------------------------------
    def _client(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
            self._session.headers.update({
                "apikey": self.key,
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=merge-duplicates,return=minimal",
            })
        return self._session

    def _rpc(self, table: str, method: str = "GET", payload=None, params=None):
        session = self._client()
        url = f"{self.url}/rest/v1/{table}"
        response = session.request(method, url, json=payload, params=params, timeout=20)
        if response.status_code >= 400:
            raise RuntimeError(
                f"{table} {method} failed: HTTP {response.status_code} {response.text[:200]}"
            )
        if not response.content:
            return []
        return response.json()

    @staticmethod
    def _article_payload(rec: ArticleRecord) -> Dict[str, Any]:
        data = asdict(rec)
        for key in ("published_at", "first_seen_at", "processed_at"):
            data[key] = data[key] or None
        return data

    @staticmethod
    def _story_payload(rec: StoryRecord) -> Dict[str, Any]:
        data = asdict(rec)
        for key in ("first_seen_at", "last_seen_at", "first_sent_at"):
            data[key] = data[key] or None
        return data

    @staticmethod
    def _signal_payload(rec: SignalRecord) -> Dict[str, Any]:
        data = asdict(rec)
        data["market_price_asof"] = data["market_price_asof"] or None
        return data

    # -- interface ---------------------------------------------------------
    def health_check(self) -> Tuple[bool, str]:
        try:
            self._rpc("stories", "GET", params={"select": "story_key", "limit": 1})
            return True, f"reachable: {self.url}"
        except Exception as exc:
            return False, f"unreachable: {exc}"

    def ensure_schema(self) -> Tuple[bool, str]:
        """Create tables if absent.

        PostgREST cannot run DDL, so this uses the Supabase ``pg_meta`` query
        endpoint when available. Failure is non-fatal: a pre-created schema is
        the normal case.
        """
        try:
            session = self._client()
            response = session.post(
                f"{self.url}/rest/v1/rpc/exec_sql",
                json={"sql": _SUPABASE_SCHEMA},
                timeout=30,
            )
            if response.status_code < 400:
                return True, "schema created"
            return False, f"exec_sql unavailable (HTTP {response.status_code})"
        except Exception as exc:
            return False, f"schema creation skipped: {exc}"

    def upsert_articles(self, records: Iterable[ArticleRecord]) -> int:
        payloads = [self._article_payload(r) for r in records if r.canonical_url]
        if not payloads:
            return 0
        self._rpc("articles", "POST", payload=payloads)
        for rec in records:
            self._articles[rec.canonical_url] = rec
        return len(payloads)

    def get_article(self, canonical_url: str) -> Optional[ArticleRecord]:
        if canonical_url in self._articles:
            return self._articles[canonical_url]
        rows = self._rpc(
            "articles", "GET",
            params={"canonical_url": f"eq.{canonical_url}", "select": "*", "limit": 1},
        )
        if not rows:
            return None
        rec = ArticleRecord.from_dict(rows[0])
        self._articles[canonical_url] = rec
        return rec

    def upsert_stories(self, records: Iterable[StoryRecord]) -> int:
        payloads = [self._story_payload(r) for r in records if r.story_key]
        if not payloads:
            return 0
        self._rpc("stories", "POST", payload=payloads)
        for rec in records:
            self._stories[rec.story_key] = rec
        return len(payloads)

    def get_story(self, story_key: str) -> Optional[StoryRecord]:
        if story_key in self._stories:
            return self._stories[story_key]
        rows = self._rpc(
            "stories", "GET",
            params={"story_key": f"eq.{story_key}", "select": "*", "limit": 1},
        )
        if not rows:
            return None
        rec = StoryRecord.from_dict(rows[0])
        self._stories[story_key] = rec
        return rec

    def record_signals(self, records: Iterable[SignalRecord]) -> int:
        payloads = [self._signal_payload(r) for r in records]
        if not payloads:
            return 0
        self._rpc("signals", "POST", payload=payloads)
        for rec in records:
            self._signals[rec.signal_id] = rec
        return len(payloads)

    def mark_signal_sent(self, signal_id: str) -> bool:
        try:
            self._rpc(
                "signals", "PATCH",
                payload={"sent": 1},
                params={"signal_id": f"eq.{signal_id}"},
            )
            if signal_id in self._signals:
                self._signals[signal_id].sent = 1
            return True
        except Exception as exc:
            logger.error("mark_signal_sent(%s) failed: %s", signal_id, exc)
            return False

    def sent_story_keys(self) -> set:
        rows = self._rpc(
            "stories", "GET",
            params={"sent_count": "gt.0", "select": "story_key"},
        )
        return {r["story_key"] for r in rows}

    def recent_articles(self, hours: int = 48, limit: int = 500) -> List[ArticleRecord]:
        since = iso(utcnow() - timedelta(hours=hours))
        rows = self._rpc(
            "articles", "GET",
            params={
                "first_seen_at": f"gte.{since}",
                "select": "*",
                "order": "first_seen_at.desc",
                "limit": str(limit),
            },
        )
        return [ArticleRecord.from_dict(r) for r in rows]

    def recent_signals(self, days: int = 30, limit: int = 200) -> List[SignalRecord]:
        since = iso(utcnow() - timedelta(days=days))
        rows = self._rpc(
            "signals", "GET",
            params={
                "generated_at": f"gte.{since}",
                "select": "*",
                "order": "generated_at.desc",
                "limit": str(limit),
            },
        )
        return [SignalRecord.from_dict(r) for r in rows]

    def recent_signals_for_ticker(self, ticker: str, hours: int = 48) -> List[SignalRecord]:
        since = iso(utcnow() - timedelta(hours=hours))
        rows = self._rpc(
            "signals", "GET",
            params={
                "ticker": f"eq.{ticker}",
                "generated_at": f"gte.{since}",
                "select": "*",
                "order": "generated_at.desc",
            },
        )
        return [SignalRecord.from_dict(r) for r in rows]

    def counts(self) -> Dict[str, int]:
        out = {}
        for table in ("articles", "stories", "signals"):
            try:
                rows = self._rpc(table, "GET", params={"select": "*", "limit": 1000})
                out[table] = len(rows)
            except Exception:
                out[table] = -1
        return out

    def flush(self) -> None:
        # Writes are already durable (immediate POSTs).
        return None


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

_store: Optional[StoryStore] = None
_store_lock = threading.Lock()


def get_store(force: Optional[str] = None, root: Optional[Path] = None) -> StoryStore:
    """Return the process-wide store.

    Backend selection, in order:

    1. explicit ``force`` argument
    2. ``ALPHASCOUT_STORE`` env var (``supabase`` | ``git``)
    3. ``SUPABASE_URL`` + ``SUPABASE_KEY`` both present -> Supabase
    4. otherwise -> git-state
    """
    global _store
    with _store_lock:
        if _store is not None and force is None:
            return _store

        choice = (force or os.getenv("ALPHASCOUT_STORE", "")).strip().lower()
        url = (os.getenv("SUPABASE_URL") or "").strip()
        key = (os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

        if choice == "git" or (not choice and not (url and key)):
            store: StoryStore = GitStateStore(root=root)
        elif url and key:
            store = SupabaseStore(url, key)
        else:
            logger.warning(
                "ALPHASCOUT_STORE=%s but SUPABASE_URL/SUPABASE_KEY missing; "
                "falling back to git-state store",
                choice,
            )
            store = GitStateStore(root=root)

        if force is None:
            _store = store
        logger.info("StoryStore backend: %s", store.name)
        return store


def reset_store() -> None:
    """Drop the cached singleton. Used by tests."""
    global _store
    with _store_lock:
        _store = None
