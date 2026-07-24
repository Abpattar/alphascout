"""
Small-Cap Screener Module
Finds active small-caps with unusual activity from Screener.in, Trendlyne, and NSE
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class ScreenerCandidate:
    ticker: str
    name: str
    price: float
    change_pct: float
    volume_lakh: float
    market_cap_cr: float
    source: str
    reason: str  # Why this stock is interesting
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "price": self.price,
            "change_pct": self.change_pct,
            "volume_lakh": self.volume_lakh,
            "market_cap_cr": self.market_cap_cr,
            "source": self.source,
            "reason": self.reason,
            "fetched_at": self.fetched_at,
        }


def scan_for_active_smallcaps(max_results: int = 20) -> List[ScreenerCandidate]:
    """
    Scan multiple sources for active small-caps with unusual activity.
    Returns candidates sorted by activity level.
    """
    candidates = []

    # Source 1: NSE top gainers (small-cap filter)
    try:
        nse = _scan_nse_gainers()
        candidates.extend(nse)
        logger.info(f"NSE: found {len(nse)} small-cap gainers")
    except Exception as e:
        logger.debug(f"NSE scan failed: {e}")

    # Source 2: Screener.in cheap ideas / value picks
    try:
        screener = _scan_screener_ideas()
        candidates.extend(screener)
        logger.info(f"Screener.in: found {len(screener)} candidates")
    except Exception as e:
        logger.debug(f"Screener.in scan failed: {e}")

    # Source 3: Trendlyne small/mid cap movers
    try:
        trendlyne = _scan_trendlyne_movers()
        candidates.extend(trendlyne)
        logger.info(f"Trendlyne: found {len(trendlyne)} candidates")
    except Exception as e:
        logger.debug(f"Trendlyne scan failed: {e}")

    # Deduplicate by ticker
    seen = set()
    unique = []
    for c in candidates:
        if c.ticker not in seen:
            seen.add(c.ticker)
            unique.append(c)

    # Sort by absolute change % (most active first)
    unique.sort(key=lambda c: abs(c.change_pct), reverse=True)

    logger.info(f"Total unique screener candidates: {len(unique)}")
    return unique[:max_results]


def get_screener_candidates() -> List[ScreenerCandidate]:
    """Alias for scan_for_active_smallcaps"""
    return scan_for_active_smallcaps()


def _scan_nse_gainers() -> List[ScreenerCandidate]:
    """Fetch NSE top gainers and filter for small-caps"""
    candidates = []

    try:
        # NSE API for top gainers
        url = "https://www.nseindia.com/api/live-analysis-variations?index=gainers"
        session = requests.Session()
        session.headers.update(HEADERS)
        # NSE needs a cookie first
        session.get("https://www.nseindia.com", timeout=10)
        resp = session.get(url, timeout=10)

        if resp.status_code != 200:
            return []

        data = resp.json()
        for item in data.get("data", [])[:50]:
            symbol = item.get("symbol", "")
            ltp = item.get("ltp", 0)
            change = item.get("change", 0)
            pchange = item.get("pChange", 0)
            volume = item.get("volume", 0)

            # Filter: small-cap price range
            if not (30 <= ltp <= 600):
                continue

            # Estimate market cap (rough: volume * price as proxy for liquidity)
            vol_lakh = volume / 100000 if volume else 0

            candidates.append(ScreenerCandidate(
                ticker=f"{symbol}.NS",
                name=symbol,
                price=ltp,
                change_pct=pchange,
                volume_lakh=round(vol_lakh, 1),
                market_cap_cr=0,  # Will be filled later if needed
                source="nse_gainers",
                reason=f"Top gainer +{pchange:.1f}%",
                fetched_at=datetime.now().isoformat(),
            ))

    except Exception as e:
        logger.debug(f"NSE gainers failed: {e}")

    return candidates


def _scan_screener_ideas() -> List[ScreenerCandidate]:
    """Fetch from Screener.in screens (cheap ideas, value picks)"""
    candidates = []

    screens = [
        ("https://www.screener.in/screens/cheap-ideas/", "Cheap ideas - undervalued small-caps"),
        ("https://www.screener.in/screens/high-growth/", "High growth small-caps"),
    ]

    session = requests.Session()
    session.headers.update(HEADERS)

    for url, reason in screens:
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # Parse table rows
            for row in soup.select("table.data-table tbody tr"):
                link = row.select_one("td a[href*='/company/']")
                if not link:
                    continue

                name = link.get_text(strip=True)
                href = link.get("href", "")

                # Extract ticker from href (e.g., /company/RELIANCE/ -> RELIANCE)
                parts = href.strip("/").split("/")
                if len(parts) >= 2:
                    ticker_base = parts[-1].upper()
                else:
                    continue

                # Get price from cells
                cells = row.select("td")
                price = 0
                change_pct = 0
                if len(cells) >= 3:
                    try:
                        price = float(cells[1].get_text(strip=True).replace(",", ""))
                        change_text = cells[2].get_text(strip=True).replace(",", "").replace("%", "")
                        change_pct = float(change_text)
                    except (ValueError, IndexError):
                        pass

                # Filter small-cap price
                if not (30 <= price <= 600):
                    continue

                candidates.append(ScreenerCandidate(
                    ticker=f"{ticker_base}.NS",
                    name=name,
                    price=price,
                    change_pct=change_pct,
                    volume_lakh=0,
                    market_cap_cr=0,
                    source="screener_in",
                    reason=reason,
                    fetched_at=datetime.now().isoformat(),
                ))

            time.sleep(1)  # Rate limit

        except Exception as e:
            logger.debug(f"Screener.in failed for {url}: {e}")

    return candidates


def _scan_trendlyne_movers() -> List[ScreenerCandidate]:
    """Fetch small/mid cap movers from Trendlyne"""
    candidates = []

    try:
        url = "https://trendlyne.com/equity/market-stats/top-gainers-loser/"
        resp = requests.get(url, headers=HEADERS, timeout=10)

        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # Find gainers table
        for row in soup.select("table tbody tr"):
            cells = row.select("td")
            if len(cells) < 4:
                continue

            # Extract ticker and name
            link = row.select_one("a[href*='/equity/']")
            if not link:
                continue

            href = link.get("href", "")
            name = link.get_text(strip=True)

            # Extract ticker from href
            match = re.search(r'/equity/([A-Z0-9]+)', href)
            if not match:
                continue
            ticker_base = match.group(1)

            # Get price and change
            try:
                price = float(cells[1].get_text(strip=True).replace(",", ""))
                change_text = cells[2].get_text(strip=True).replace(",", "").replace("%", "")
                change_pct = float(change_text)
            except (ValueError, IndexError):
                continue

            # Filter small-cap
            if not (30 <= price <= 600):
                continue

            candidates.append(ScreenerCandidate(
                ticker=f"{ticker_base}.NS",
                name=name,
                price=price,
                change_pct=change_pct,
                volume_lakh=0,
                market_cap_cr=0,
                source="trendlyne",
                reason=f"Gainer +{change_pct:.1f}%",
                fetched_at=datetime.now().isoformat(),
            ))

    except Exception as e:
        logger.debug(f"Trendlyne failed: {e}")

    return candidates


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    candidates = scan_for_active_smallcaps()
    print(f"\nFound {len(candidates)} candidates:")
    for c in candidates:
        print(f"  {c.ticker:15s} | ₹{c.price:8.2f} | {c.change_pct:+6.1f}% | {c.source:15s} | {c.reason}")
