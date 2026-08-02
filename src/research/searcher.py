"""
Web Research Searcher
Fetches recent news around a catalyst event via free RSS endpoints
(Google News + Bing News). Used by the pipeline to narrow down beneficiary
companies when an article names no company but involves money + a decision.
"""
import html
import logging
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote

import feedparser
import requests

from src.config import get_setting

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _query_urls(query: str, freshness_days: int) -> List[str]:
    q = quote(query)
    when = f"when:{freshness_days}d" if freshness_days and freshness_days > 0 else ""
    google_q = quote(f"{query} {when}".strip())
    return [
        f"https://news.google.com/rss/search?q={google_q}&hl=en-IN&gl=IN&ceid=IN:en",
        f'https://www.bing.com/news/search?q={q}&format=RSS&qft=interval%3d%22{freshness_days}%22',
    ]


def _rank_keywords(query: str) -> List[str]:
    stop = {
        "the", "a", "an", "for", "and", "of", "to", "in", "on", "with", "by",
        "india", "indian", "government", "govt", "crore", "rs", "order", "news",
    }
    words = re.findall(r"[a-z]{3,}", query.lower())
    return [w for w in words if w not in stop]


def _entry_score(entry: dict, keywords: List[str]) -> int:
    text = f"{entry.get('title', '')} {entry.get('snippet', '')}".lower()
    return sum(1 for kw in keywords if kw in text)


def _fetch_feed(url: str, timeout: int) -> List[dict]:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENTS[0], "Accept": "application/rss+xml, text/xml, */*"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.debug(f"Research feed {url} -> {resp.status_code}")
            return []
        feed = feedparser.parse(resp.text)
    except Exception as e:
        logger.debug(f"Research feed fetch failed {url}: {e}")
        return []

    results = []
    for e in feed.entries:
        source = ""
        if hasattr(e, "source") and getattr(e.source, "title", None):
            source = e.source.title
        elif e.get("source"):
            source = e["source"].get("title", "")
        snippet = _strip_html(e.get("summary", e.get("description", "")) or "")[:400]
        results.append({
            "title": _strip_html(e.get("title", ""))[:200],
            "link": e.get("link", ""),
            "source": source,
            "published": e.get("published", e.get("updated", "")),
            "snippet": snippet,
        })
    return results


def research_news(
    query: str,
    max_results: int = 8,
    freshness_days: Optional[int] = None,
    timeout: int = 8,
) -> List[Dict]:
    """
    Search recent news for a catalyst event.

    Returns up to max_results dicts:
      {title, link, source, published, snippet, _score}
    """
    cfg = get_setting("research", {})
    if not isinstance(cfg, dict):
        cfg = {}
    if freshness_days is None:
        freshness_days = int(cfg.get("freshness_days", 7))
    if max_results is None:
        max_results = int(cfg.get("max_results", 8))

    keywords = _rank_keywords(query)
    all_entries: Dict[str, dict] = {}

    start = time.time()
    for url in _query_urls(query, freshness_days):
        for e in _fetch_feed(url, timeout):
            title = e["title"]
            if not title:
                continue
            key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()[:80]
            e["_score"] = _entry_score(e, keywords)
            e["_published"] = e.get("published", "")
            if key and (key not in all_entries or e["_score"] > all_entries[key]["_score"]):
                all_entries[key] = e
        if time.time() - start > 15:
            break

    ranked = sorted(all_entries.values(), key=lambda e: e["_score"], reverse=True)
    ranked.sort(key=lambda e: e["_score"], reverse=True)

    results = []
    for e in ranked:
        if e["_score"] == 0 and len(results) >= 3:
            continue
        results.append({k: v for k, v in e.items() if not k.startswith("_")})
        if len(results) >= max_results:
            break

    logger.info(f"Research '{query}': {len(results)} results from {len(all_entries)} fetched")
    return results
