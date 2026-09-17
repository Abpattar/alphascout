"""
AlphaScout News Scraper - Config-Driven Version
Sources loaded from config/sources.yaml
Uses RSS + HTML + API fallbacks
"""
import asyncio
import aiohttp
import feedparser
import hashlib
import json
import logging
import random
import re
import sys
import time
import yaml

from pathlib import Path

# Force IPv4 resolution — broken IPv6 routing makes HTTP calls hang
try:
    from src.netfix import force_ipv4
except ImportError:  # direct-script execution
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from netfix import force_ipv4
force_ipv4()

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]

# Defence & market keywords for filtering
DEFENCE_KW = [
    "defence", "defense", "military", "army", "navy", "air force",
    "hal", "bel", "bdl", "drdo", "brahmos", "tejas", "dhruv",
    "missile", "fighter", "submarine", "warship", "procurement",
    "contract", "order", "indigenous", "atmanirbhar", "make in india",
    "ministry of defence", "mod", "defence export", "defence deal",
]
MARKET_KW = [
    "stock", "share", "market", "nse", "bse", "sensex", "nifty",
    "ipo", "qip", "buyback", "dividend", "earnings", "results",
    "profit", "revenue", "order", "contract", "deal", "acquisition",
    "merger", "expansion", "capex", "investment", "pli",
    "production linked incentive", "export", "partnership",
    "small cap", "mid cap", "micro cap", "multibagger",
    "railway", "ev", "solar", "renewable", "infrastructure",
    "chemical", "pharma", "logistics", "manufacturing",
]
EXCLUDE_KW = [
    "cinema", "movie", "actor", "actress", "film", "bollywood",
    "cricket", "football", "sports", "ipl", "match", "tournament",
    "teacher", "school", "college", "admit card", "exam", "uptet",
    "cheetah", "wildlife", "leopard", "tiger", "animal",
    "marriage", "wedding", "festival", "recipe", "cooking",
]


def _merge_keywords_from_config():
    """Merge the keyword lists from config/sources.yaml into the module lists
    (config is the single source of truth for extra terms)."""
    global DEFENCE_KW, MARKET_KW, EXCLUDE_KW
    try:
        with open(CONFIG_DIR / "sources.yaml") as f:
            data = yaml.safe_load(f)
        defc = [str(k).lower() for k in data.get("defence_keywords", [])]
        mkt = [str(k).lower() for k in data.get("market_keywords", [])]
        exc = [str(k).lower() for k in data.get("exclude_keywords", [])]
        if defc:
            DEFENCE_KW = list(dict.fromkeys(DEFENCE_KW + defc))
        if mkt:
            MARKET_KW = list(dict.fromkeys(MARKET_KW + mkt))
        if exc:
            EXCLUDE_KW = list(dict.fromkeys(EXCLUDE_KW + exc))
    except Exception:
        pass


_merge_keywords_from_config()


def _build_kw_patterns() -> Dict[str, "re.Pattern"]:
    """Short keywords (<=4 chars) are matched as whole words so 'mod' never
    matches 'modern', 'bel' never matches 'believe', etc."""
    pats = {}
    for kw in DEFENCE_KW + MARKET_KW:
        if len(kw) <= 4:
            pats[kw] = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
    return pats


_KW_PATTERNS = _build_kw_patterns()


@dataclass
class Article:
    title: str
    url: str
    source: str
    category: str
    published: str = ""
    content: str = ""
    summary: str = ""
    fetched_at: str = ""
    content_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        return cls(**d)


def is_relevant(title: str, content: str = "") -> bool:
    text = (title + " " + content).lower()
    if any(ex in text for ex in EXCLUDE_KW):
        return False
    for kw in DEFENCE_KW + MARKET_KW:
        pat = _KW_PATTERNS.get(kw)
        if pat:
            if pat.search(text):
                return True
        elif kw in text:
            return True
    return False


def get_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }


# ─────────────────────────────────────────────────────────────────────────
# ARTICLE-URL QUALITY FILTERS
# HTML listing pages are full of menu/nav/category links that are not
# articles. These helpers drop them so the scraper only keeps real stories.
# ─────────────────────────────────────────────────────────────────────────

_JUNK_URL_SEGMENTS = {
    "about", "topic", "tag", "tags", "category", "categories", "section",
    "feed", "feeds", "screens", "screen", "login", "signup", "register",
    "privacy", "terms", "terms-of-use", "advertise", "advertising", "contact",
    "newsletter", "store", "app", "help", "faq", "careers", "sitemap", "rss",
    "podcast", "videos", "photogallery", "trending", "market-activity",
    "most-active", "top-gainers", "top-losers", "unlisted-shares", "calendar",
    "upcoming-ipos", "ipo-list", "stock-brokers", "corporate", "analysis",
    "opinion", "editorial", "author", "authors", "search", "results",
}
_ARTICLE_URL_ID_RE = re.compile(r"\d{5,}")
_ARTICLE_URL_DATE_RE = re.compile(r"/(?:19|20)\d{2}/\d{1,2}/\d{1,2}/")
_ARTICLE_URL_TOKENS = {
    "articleshow", "story", "stories", "article", "news", "companies",
    "business", "defence", "market", "markets", "company", "stock",
    "result", "economy", "industry", "blog",
}
_JUNK_TITLES = {
    "stock market news", "most active stocks", "trending stocks",
    "unlisted shares", "market turnover", "markets calendar",
    "recent ipos list", "stock companies list", "defence industry",
    "defence dialogue", "national security", "latest news", "top stories",
    "read more", "popular", "top gainers", "top losers", "scheduled orders",
    "more news", "related stories", "recommended", "you may also like",
}


def _is_article_url(href: str) -> bool:
    """True if href looks like a real news article (not a menu/category page)."""
    lower = href.lower()
    try:
        path = urlparse(lower).path
    except Exception:
        path = lower
    segs = [s for s in path.split("/") if s]
    if any(s in _JUNK_URL_SEGMENTS for s in segs):
        return False
    if _ARTICLE_URL_ID_RE.search(path) or _ARTICLE_URL_DATE_RE.search(path):
        return True
    return any(seg in _ARTICLE_URL_TOKENS for seg in segs)


def _is_junk_title(title: str) -> bool:
    return title.strip().lower() in _JUNK_TITLES


_BASE_SELECTORS = [
    "article", ".article-body", "main", ".post-content", ".entry-content",
    "#content", ".news-content", ".story-content", ".article__content",
    ".Normal", ".articlebodycontent", ".content-para", ".detail-content",
]


def _load_enrichment_selectors() -> List[str]:
    try:
        with open(CONFIG_DIR / "sources.yaml") as f:
            data = yaml.safe_load(f)
        sels = data.get("enrichment_selectors", []) or []
        return [s for s in sels if s]
    except Exception:
        return []


_ARTICLE_SELECTORS = list(dict.fromkeys(_load_enrichment_selectors() + _BASE_SELECTORS))


def extract_content(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for sel in _ARTICLE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(" ", strip=True)
            if len(text) > 200:
                return text[:3000]
    paras = soup.find_all("p")
    text = " ".join(p.get_text(strip=True) for p in paras[:15])
    return text[:3000] if len(text) > 100 else ""


# ─────────────────────────────────────────────────────────────────────────
# SOURCE LOADING FROM CONFIG
# ─────────────────────────────────────────────────────────────────────────

def load_sources_from_config() -> List[dict]:
    """Load sources from config/sources.yaml and convert to internal format"""
    config_path = CONFIG_DIR / "sources.yaml"
    if not config_path.exists():
        logger.warning(f"sources.yaml not found at {config_path}, using minimal fallback")
        return _get_fallback_sources()

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Failed to load sources.yaml: {e}")
        return _get_fallback_sources()

    sources = []
    for src in data.get("sources", []):
        if not src.get("enabled", True):
            continue

        # Convert YAML format to internal format
        source_type = src.get("type", "rss_html")
        rss_url = src.get("rss_url") if source_type != "html_only" else None
        html_urls = src.get("html_urls", []) if source_type != "rss_only" else []

        sources.append({
            "name": src["name"],
            "category": src.get("category", "market"),
            "tier": src.get("tier", 3),
            "rss": rss_url,
            "html": html_urls,
            "selectors": src.get("selectors", ["h2 a", "h3 a"]),
            "base": src.get("base_url", ""),
            "rate_limit": src.get("rate_limit", 10),
            "priority": src.get("priority", "normal"),
            "note": src.get("note", ""),
        })

    logger.info(f"Loaded {len(sources)} sources from config")
    return sources


def _get_fallback_sources() -> List[dict]:
    """Minimal fallback sources if config is missing"""
    return [
        {
            "name": "economic_times",
            "category": "mainstream",
            "rss": "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
            "html": [],
            "selectors": [],
            "base": "https://economictimes.indiatimes.com",
        },
        {
            "name": "moneycontrol",
            "category": "market",
            "rss": "https://www.moneycontrol.com/rss/marketreports.xml",
            "html": [],
            "selectors": [],
            "base": "https://www.moneycontrol.com",
        },
    ]


SOURCES = load_sources_from_config()


# ─────────────────────────────────────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────────────────────────────────────

class NewsScraper:
    def __init__(self):
        self.articles: List[Article] = []
        self.seen_hashes: Set[str] = set()

    async def scrape_all(self, categories: List[str] = None, max_per_source: int = 15) -> List[Article]:
        sources = SOURCES
        if categories:
            sources = [s for s in sources if s["category"] in categories]

        logger.info(f"Scraping {len(sources)} sources...")

        timeout = aiohttp.ClientTimeout(total=20)
        connector = aiohttp.TCPConnector(limit=10, ssl=False)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            tasks = [self._fetch_source(session, src, max_per_source) for src in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        all_articles = []
        for i, result in enumerate(results):
            if isinstance(result, list):
                all_articles.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"{sources[i]['name']}: {result}")

        # Deduplicate
        unique = self._deduplicate(all_articles)

        # Sort by relevance
        unique.sort(key=lambda a: self._score(a), reverse=True)

        logger.info(f"Total unique articles: {len(unique)}")
        return unique

    async def _fetch_source(self, session: aiohttp.ClientSession, src: dict, max_items: int) -> List[Article]:
        articles = []

        # Try RSS first
        if src.get("rss"):
            rss_articles = await self._fetch_rss(session, src)
            articles.extend(rss_articles)

        # If not enough (or a tier-1 government source), try HTML
        if src.get("html") and (len(articles) < 5 or src.get("category") == "government"):
            html_articles = await self._fetch_html(session, src)
            articles.extend(html_articles)

        return articles[:max_items]

    async def _fetch_rss(self, session: aiohttp.ClientSession, src: dict) -> List[Article]:
        articles = []
        try:
            async with session.get(src["rss"], headers=get_headers()) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()

            feed = feedparser.parse(text)
            for entry in feed.entries[:25]:
                title = entry.get("title", "").strip()
                url = entry.get("link", "").strip()
                summary = BeautifulSoup(
                    entry.get("summary", "") or entry.get("description", ""), "lxml"
                ).get_text(strip=True)[:500]
                published = entry.get("published", "")

                if not title or not url:
                    continue
                if not is_relevant(title, summary):
                    continue

                articles.append(Article(
                    title=title, url=url, source=src["name"],
                    category=src["category"], published=published,
                    summary=summary, fetched_at=datetime.now().isoformat()
                ))
        except Exception as e:
            logger.debug(f"RSS failed for {src['name']}: {e}")

        return articles

    async def _fetch_html(self, session: aiohttp.ClientSession, src: dict) -> List[Article]:
        articles = []
        seen = set()

        for url in src.get("html", []):
            try:
                async with session.get(url, headers=get_headers()) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()

                soup = BeautifulSoup(html, "lxml")
                for sel in src.get("selectors", ["h2 a", "h3 a"]):
                    for a in soup.select(sel):
                        title = a.get_text(strip=True)
                        href = a.get("href", "")

                        if not title or not href or len(title) < 15:
                            continue
                        if _is_junk_title(title) or not _is_article_url(href):
                            continue
                        if not href.startswith("http"):
                            href = urljoin(src["base"], href)
                        if href in seen:
                            continue
                        if not is_relevant(title):
                            continue

                        seen.add(href)
                        articles.append(Article(
                            title=title, url=href, source=src["name"],
                            category=src["category"],
                            fetched_at=datetime.now().isoformat()
                        ))

                        if len(articles) >= 10:
                            break
            except Exception as e:
                logger.debug(f"HTML failed for {src['name']}: {e}")

        return articles

    async def enrich_articles(self, articles: List[Article], max_enrich: int = 15) -> List[Article]:
        timeout = aiohttp.ClientTimeout(total=8)
        connector = aiohttp.TCPConnector(limit=5, ssl=False)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async def enrich_one(a: Article) -> Article:
                if a.content and len(a.content) > 200:
                    return a
                try:
                    async with session.get(a.url, headers=get_headers()) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            a.content = extract_content(html)
                            a.content_hash = hashlib.md5(a.content.encode()).hexdigest()[:16]
                except:
                    pass
                return a

            tasks = [enrich_one(a) for a in articles[:max_enrich]]
            enriched = await asyncio.gather(*tasks, return_exceptions=True)

        return [a for a in enriched if isinstance(a, Article)]

    def _deduplicate(self, articles: List[Article]) -> List[Article]:
        unique = []
        seen_titles = set()
        seen_urls = set()

        for a in articles:
            url_key = a.url.split("?")[0].lower()
            title_key = self._norm_title(a.title)

            if url_key in seen_urls or title_key in seen_titles:
                continue

            seen_urls.add(url_key)
            seen_titles.add(title_key)
            unique.append(a)

        return unique

    def _norm_title(self, title: str) -> str:
        title = re.sub(r'^(breaking|exclusive|update|live|video):\s*', '', title, flags=re.I)
        title = re.sub(r'[^a-z0-9\s]', '', title.lower())
        return " ".join(title.split()[:10])

    def _score(self, article: Article) -> float:
        text = (article.title + " " + article.summary).lower()
        score = 0
        for kw in DEFENCE_KW:
            if kw in text:
                score += 3
        for kw in MARKET_KW:
            if kw in text:
                score += 2
        if article.category == "government":
            score += 5
        if article.category == "market":
            score += 3
        return score

    def _save_cache(self, articles: List[Article]):
        cache_file = Path(__file__).parent.parent.parent / "data" / "articles_cache.json"
        cache_file.parent.mkdir(exist_ok=True)
        data = {
            "fetched_at": datetime.now().isoformat(),
            "articles": [a.to_dict() for a in articles]
        }
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)

    def load_cache(self, max_age_hours: int = 12) -> List[Article]:
        cache_file = Path(__file__).parent.parent.parent / "data" / "articles_cache.json"
        if not cache_file.exists():
            return []
        try:
            with open(cache_file) as f:
                data = json.load(f)
            fetched = datetime.fromisoformat(data.get("fetched_at", ""))
            if datetime.now() - fetched > timedelta(hours=max_age_hours):
                return []
            return [Article.from_dict(a) for a in data.get("articles", [])]
        except:
            return []


# ─────────────────────────────────────────────────────────────────────────
# SYNC WRAPPER
# ─────────────────────────────────────────────────────────────────────────

def _run_async_or_thread(coro, timeout: int):
    """Run a coroutine on this thread's loop, or in a worker thread when an
    event loop is already running. Never mutates the caller's loop."""
    try:
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=timeout)
    except RuntimeError:
        return asyncio.run(coro)


def _get_scrape_config() -> dict:
    try:
        from src.config import load_settings
        return load_settings().get("scraping", {}) or {}
    except Exception:
        return {}


def scrape_all_sources(categories: List[str] = None, use_cache: bool = True) -> List[Article]:
    scraper = NewsScraper()

    if use_cache:
        cached = scraper.load_cache()
        if cached:
            logger.info(f"Using {len(cached)} cached articles")
            return cached

    cfg = _get_scrape_config()
    max_per_source = int(cfg.get("max_articles_per_source", 20) or 20)
    enrich_top_n = int(cfg.get("enrich_top_n", 15) or 15)

    try:
        articles = _run_async_or_thread(
            scraper.scrape_all(categories=categories, max_per_source=max_per_source),
            timeout=120,
        )
    except Exception as e:
        logger.error(f"News scrape failed: {e}")
        return []

    if articles:
        try:
            enriched = _run_async_or_thread(
                scraper.enrich_articles(articles, max_enrich=enrich_top_n), timeout=90
            )
            # Merge enrichment back into the FULL list — never let enrichment
            # shrink the article set (the pipeline only sees what we return).
            enriched_by_url = {a.url: a for a in enriched if isinstance(a, Article) and a.url}
            articles = [enriched_by_url.get(a.url, a) for a in articles]
        except Exception as e:
            logger.warning(f"Enrichment failed (keeping scraped articles as-is): {e}")
        scraper._save_cache(articles)

    # Persist to database for backtesting and calibration
    try:
        from src.storage.db import get_db
        db = get_db()
        db.store_articles_batch([a.to_dict() for a in articles])
    except Exception as e:
        logger.debug(f"DB store articles failed (non-fatal): {e}")

    return articles


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    articles = scrape_all_sources(use_cache=False)
    for a in articles[:10]:
        print(f"[{a.category}] {a.source}: {a.title[:80]}")
