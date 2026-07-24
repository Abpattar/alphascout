"""
Dynamic Universe Builder
Scans Screener.in, NSE, and sector mappings to build tradeable universe
Price: ₹50-500 | Market Cap: ₹100-5000 Cr | Liquidity: >₹50L/day
"""
import json
import logging
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests
import yfinance as yf
from bs4 import BeautifulSoup

from src.config import get_all_sector_tickers, get_all_sector_keywords, DATA_DIR

logger = logging.getLogger(__name__)

UNIVERSE_CACHE = DATA_DIR / "universe_cache.json"
UNIVERSE_TTL_DAYS = 7


@dataclass
class Stock:
    ticker: str
    name: str
    sector: str
    price: float
    market_cap_cr: float
    avg_volume_lakh: float
    last_updated: str
    keywords: List[str]
    exchange: str = "NSE"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Stock":
        return cls(**d)


class UniverseBuilder:
    """Builds and maintains the tradeable stock universe"""

    def __init__(self):
        self.universe: Dict[str, Stock] = {}
        self.sector_keywords = get_all_sector_keywords()
        self.sector_tickers = get_all_sector_tickers()

    def build(self, force_refresh: bool = False) -> Dict[str, Stock]:
        """Build universe from multiple sources"""
        if not force_refresh and self._load_cache():
            logger.info(f"Loaded {len(self.universe)} stocks from cache")
            return self.universe

        logger.info("Building universe from scratch...")

        # 1. Get known tickers from sector config
        known_tickers = self._get_all_known_tickers()

        # 2. Discover from Screener.in queries
        screener_tickers = self._discover_from_screener()

        # 3. Combine and validate
        all_tickers = known_tickers | screener_tickers
        logger.info(f"Validating {len(all_tickers)} candidate tickers...")

        # 4. Fetch fundamental data in parallel
        validated = self._validate_tickers(all_tickers)

        # 5. Apply filters
        filtered = self._apply_filters(validated)

        # 6. Enrich with keywords
        self._enrich_keywords(filtered)

        # 7. Save
        self.universe = filtered
        self._save_cache()

        logger.info(f"Universe built: {len(self.universe)} tradeable stocks")
        return self.universe

    def _get_all_known_tickers(self) -> Set[str]:
        """Get all tickers from sector config (try both NSE and BSE)"""
        tickers = set()
        for sector_tickers in self.sector_tickers.values():
            for t in sector_tickers:
                if not t.endswith(".NS") and not t.endswith(".BO"):
                    tickers.add(t + ".NS")
                    tickers.add(t + ".BO")
                else:
                    tickers.add(t)
        return tickers

    def _discover_from_screener(self) -> Set[str]:
        """Discover new tickers from Screener.in queries"""
        discovered = set()

        queries = [
            "marketcap:100to5000",
            "price:50to500",
            "volume:>5000000",
        ]

        for query in queries:
            try:
                url = f"https://www.screener.in/screens/?q={query}"
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                soup = BeautifulSoup(resp.text, "lxml")

                # Parse table rows
                for row in soup.select("table.data-table tr"):
                    link = row.select_one("td a[href*='/company/']")
                    if link:
                        ticker = link["href"].split("/")[-1].upper()
                        if ticker.endswith(".NS"):
                            discovered.add(ticker)
                        elif "." not in ticker:
                            discovered.add(f"{ticker}.NS")

                time.sleep(1)  # Rate limit

            except Exception as e:
                logger.warning(f"Screener discovery failed for {query}: {e}")

        return discovered

    def _validate_tickers(self, tickers: Set[str]) -> Dict[str, Stock]:
        """Fetch and validate fundamental data, with NSE→BSE fallback"""
        validated = {}
        
        # Separate into NSE and BSE tickers
        nse_tickers = {t for t in tickers if t.endswith(".NS")}
        bse_tickers = {t for t in tickers if t.endswith(".BO")}
        
        # Group by base ticker
        base_to_nse = {t.replace(".NS", ""): t for t in nse_tickers}
        base_to_bse = {t.replace(".BO", ""): t for t in bse_tickers}
        
        # Try NSE first, then BSE for each base ticker
        all_bases = set(base_to_nse.keys()) | set(base_to_bse.keys())
        
        # Batch process in chunks
        chunk_size = 50
        base_list = list(all_bases)
        
        for i in range(0, len(base_list), chunk_size):
            chunk_bases = base_list[i:i + chunk_size]
            self._fetch_chunk_with_fallback(chunk_bases, base_to_nse, base_to_bse, validated)
            time.sleep(0.5)

        return validated

    def _fetch_chunk_with_fallback(self, bases: List[str], base_to_nse: Dict, base_to_bse: Dict, out: Dict[str, Stock]):
        """Fetch chunk with NSE→BSE fallback"""
        # Build list of tickers to try (NSE first)
        to_try = []
        for base in bases:
            if base in base_to_nse:
                to_try.append((base, base_to_nse[base], "NSE"))
            elif base in base_to_bse:
                to_try.append((base, base_to_bse[base], "BSE"))

        # Batch fetch
        tickers_str = " ".join(t[1] for t in to_try)
        try:
            data = yf.Tickers(tickers_str)
        except Exception as e:
            logger.warning(f"Batch fetch failed: {e}")
            return

        failed_nse = []
        for base, ticker, exchange in to_try:
            try:
                t = data.tickers[ticker]
                info = t.info

                if not info or info.get("regularMarketPrice") is None:
                    if exchange == "NSE":
                        failed_nse.append(base)
                    continue

                price = info.get("regularMarketPrice", 0)
                market_cap = info.get("marketCap", 0)
                volume = info.get("averageVolume", 0)

                if not (50 <= price <= 500):
                    continue
                if not (100e7 <= market_cap <= 5000e7):
                    continue
                if not (volume * price >= 50e5):
                    continue

                sector = self._classify_sector(info.get("longName", ""), info.get("sector", ""), ticker)

                out[ticker] = Stock(
                    ticker=ticker,
                    name=info.get("longName", ticker),
                    sector=sector,
                    price=price,
                    market_cap_cr=round(market_cap / 1e7, 1),
                    avg_volume_lakh=round(volume * price / 1e5, 1),
                    last_updated=datetime.now().isoformat(),
                    keywords=[],
                    exchange=exchange
                )

            except Exception as e:
                logger.debug(f"Failed {ticker}: {e}")

        # Retry failed NSE tickers with BSE
        if failed_nse:
            bse_retry = []
            for base in failed_nse:
                if base in base_to_bse:
                    bse_retry.append((base, base_to_bse[base]))
            
            if bse_retry:
                retry_str = " ".join(t[1] for t in bse_retry)
                try:
                    retry_data = yf.Tickers(retry_str)
                    for base, ticker in bse_retry:
                        try:
                            t = retry_data.tickers[ticker]
                            info = t.info
                            if not info or info.get("regularMarketPrice") is None:
                                continue

                            price = info.get("regularMarketPrice", 0)
                            market_cap = info.get("marketCap", 0)
                            volume = info.get("averageVolume", 0)

                            if not (50 <= price <= 500):
                                continue
                            if not (100e7 <= market_cap <= 5000e7):
                                continue
                            if not (volume * price >= 50e5):
                                continue

                            sector = self._classify_sector(info.get("longName", ""), info.get("sector", ""))
                            out[ticker] = Stock(
                                ticker=ticker,
                                name=info.get("longName", ticker),
                                sector=sector,
                                price=price,
                                market_cap_cr=round(market_cap / 1e7, 1),
                                avg_volume_lakh=round(volume * price / 1e5, 1),
                                last_updated=datetime.now().isoformat(),
                                keywords=[],
                                exchange="BSE"
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

    def _classify_sector(self, name: str, yf_sector: str, ticker: str = "") -> str:
        """Classify stock into our sectors"""
        # Manual overrides for known stocks
        manual_map = {
            "GHCL.NS": "chemicals_specialty",
            "TARSONS.NS": "manufacturing_pli",
            "RAJESHEXPO.NS": "consumer",
            "JTEKTINDIA.NS": "manufacturing_pli",
            "WEBELSOLAR.NS": "renewable",
            "ASHOKA.NS": "infra",
            "MANINFRA.NS": "infra",
            "SPIC.NS": "chemicals_specialty",
            "COASTCORP.NS": "consumer",
            "DELTACORP.NS": "consumer",
            "BAJAJELEC.NS": "consumer",
            "ORIENTELEC.NS": "consumer",
        }
        if ticker in manual_map:
            return manual_map[ticker]

        text = (name + " " + yf_sector).lower()

        # Sector keywords from config
        for sector, keywords in self.sector_keywords.items():
            if any(kw.lower() in text for kw in keywords):
                return sector

        # Fallback to yfinance sector mapping
        yf_map = {
            "industrials": "manufacturing_pli",
            "basic_materials": "chemicals_specialty",
            "consumer_cyclical": "manufacturing_pli",
            "technology": "it",
            "energy": "renewable",
            "utilities": "infra",
            "financial_services": "logistics",
        }
        return yf_map.get(yf_sector.lower(), "other")

    def _apply_filters(self, stocks: Dict[str, Stock]) -> Dict[str, Stock]:
        """Apply final filters from config"""
        from src.config import get_universe_config

        config = get_universe_config()
        filtered = {}

        for ticker, stock in stocks.items():
            # Price filter
            if not (config.get("price_min", 50) <= stock.price <= config.get("price_max", 500)):
                continue

            # Market cap filter
            if not (config.get("market_cap_min_cr", 100) <= stock.market_cap_cr <= config.get("market_cap_max_cr", 5000)):
                continue

            # Volume filter
            if stock.avg_volume_lakh < config.get("min_avg_daily_volume_lakh", 50):
                continue

            filtered[ticker] = stock

        return filtered

    def _enrich_keywords(self, stocks: Dict[str, Stock]):
        """Add search keywords for each stock"""
        for ticker, stock in stocks.items():
            keywords = set()

            # Name-based
            words = re.findall(r'\b[A-Z][a-z]+\b', stock.name)
            keywords.update(w.lower() for w in words if len(w) > 3)

            # Sector keywords
            keywords.update(self.sector_keywords.get(stock.sector, []))

            # Ticker variations
            base = ticker.replace(".NS", "").replace(".BO", "")
            keywords.add(base.lower())
            keywords.add(base)

            stock.keywords = list(keywords)[:20]

    def _load_cache(self) -> bool:
        """Load universe from cache if valid"""
        if not UNIVERSE_CACHE.exists():
            return False

        try:
            with open(UNIVERSE_CACHE) as f:
                data = json.load(f)

            cached_at = datetime.fromisoformat(data.get("cached_at", ""))
            if datetime.now() - cached_at > timedelta(days=UNIVERSE_TTL_DAYS):
                return False

            self.universe = {k: Stock.from_dict(v) for k, v in data.get("universe", {}).items()}
            return True

        except Exception as e:
            logger.warning(f"Cache load failed: {e}")
            return False

    def _save_cache(self):
        """Save universe to cache"""
        data = {
            "cached_at": datetime.now().isoformat(),
            "universe": {k: v.to_dict() for k, v in self.universe.items()}
        }
        UNIVERSE_CACHE.parent.mkdir(exist_ok=True)
        with open(UNIVERSE_CACHE, "w") as f:
            json.dump(data, f, indent=2)

    def get_universe(self) -> Dict[str, Stock]:
        """Get current universe (build if needed)"""
        if not self.universe:
            self.build()
        return self.universe

    def get_by_sector(self, sector: str) -> Dict[str, Stock]:
        """Get stocks filtered by sector"""
        return {k: v for k, v in self.get_universe().items() if v.sector == sector}

    def search(self, query: str) -> List[Stock]:
        """Search universe by name/ticker/keywords"""
        query = query.lower()
        results = []
        for stock in self.get_universe().values():
            if (query in stock.ticker.lower() or
                query in stock.name.lower() or
                any(query in kw for kw in stock.keywords)):
                results.append(stock)
        return results


# Singleton
_builder: Optional[UniverseBuilder] = None


def get_universe_builder() -> UniverseBuilder:
    global _builder
    if _builder is None:
        _builder = UniverseBuilder()
    return _builder


def get_universe() -> Dict[str, Stock]:
    return get_universe_builder().get_universe()


def refresh_universe() -> Dict[str, Stock]:
    return get_universe_builder().build(force_refresh=True)


# ─────────────────────────────────────────────────────────────────────────
# ON-THE-FLY TICKER VALIDATION
# ─────────────────────────────────────────────────────────────────────────

_dynamic_cache: Dict[str, Optional[tuple]] = {}

# Known tickers for companies yfinance can't find directly
# AI often returns wrong tickers — this maps them to the correct ones
_KNOWN_TICKER_MAP = {
    "HIMADRI": "HSCL.NS",
    "HIMADRI.NS": "HSCL.NS",
    "HIMADRI.BO": "HSCL.NS",
    "HIMADRIENT": "HSCL.NS",
    "HIMADRIENT.NS": "HSCL.NS",
    "HSCL": "HSCL.NS",
    "HSCL.NS": "HSCL.NS",
    "HSCL.BO": "HSCL.NS",
    "RRPDEF": "RRPDEF.NS",
    "RRPDEF.NS": "RRPDEF.NS",
    "RRPDEFENSE": "RRPDEF.NS",
    "RRPDEFENSE.NS": "RRPDEF.NS",
    "RRPDEFENSE.BO": "RRPDEF.NS",
    "RRPDEF.BO": "RRPDEF.NS",
    "SWPEL": "SWPEL.NS",
    "SWPEL.NS": "SWPEL.NS",
    "SWPEL.BO": "SWPEL.NS",
    "PARASDEF": "PARASDEF.NS",
    "PARASDEF.NS": "PARASDEF.NS",
    "PARASDEF.BO": "PARASDEF.NS",
    "ASTRAMICRO": "ASTRAMICRO.NS",
    "ASTRAMICRO.NS": "ASTRAMICRO.NS",
    "ASTRAMICRO.BO": "ASTRAMICRO.NS",
    "ZENTEC": "ZENTEC.NS",
    "ZENTEC.NS": "ZENTEC.NS",
    "ZENTEC.BO": "ZENTEC.NS",
    "IDEAFORGE": "IDEAFORGE.NS",
    "IDEAFORGE.NS": "IDEAFORGE.NS",
    "IDEAFORGE.BO": "IDEAFORGE.NS",
    "SOLARINDS": "SOLARINDS.NS",
    "SOLARINDS.NS": "SOLARINDS.NS",
    "SOLARINDS.BO": "SOLARINDS.NS",
    "DATAPATTNS": "DATAPATTNS.NS",
    "DATAPATTNS.NS": "DATAPATTNS.NS",
    "DATAPATTNS.BO": "DATAPATTNS.NS",
    "MTARTECH": "MTARTECH.NS",
    "MTARTECH.NS": "MTARTECH.NS",
    "MTARTECH.BO": "MTARTECH.NS",
    "BEL": "BEL.NS",
    "BEL.NS": "BEL.NS",
    "BEL.BO": "BEL.NS",
    "HAL": "HAL.NS",
    "HAL.NS": "HAL.NS",
    "HAL.BO": "HAL.NS",
    "BDL": "BDL.NS",
    "BDL.NS": "BDL.NS",
    "BDL.BO": "BDL.NS",
    "COCHINSHIP": "COCHINSHIP.NS",
    "COCHINSHIP.NS": "COCHINSHIP.NS",
    "COCHINSHIP.BO": "COCHINSHIP.NS",
    "GRSE": "GRSE.NS",
    "GRSE.NS": "GRSE.NS",
    "GRSE.BO": "GRSE.NS",
    "MAZDOCK": "MAZDOCK.NS",
    "MAZDOCK.NS": "MAZDOCK.NS",
    "MAZDOCK.BO": "MAZDOCK.NS",
    "RVNL": "RVNL.NS",
    "RVNL.NS": "RVNL.NS",
    "RVNL.BO": "RVNL.NS",
    "IRFC": "IRFC.NS",
    "IRFC.NS": "IRFC.NS",
    "IRFC.BO": "IRFC.NS",
    "IRCTC": "IRCTC.NS",
    "IRCTC.NS": "IRCTC.NS",
    "IRCTC.BO": "IRCTC.NS",
    "TITAGARH": "TITAGARH.NS",
    "TITAGARH.NS": "TITAGARH.NS",
    "TITAGARH.BO": "TITAGARH.NS",
    "WAAREE": "WAAREE.NS",
    "WAAREE.NS": "WAAREE.NS",
    "WAAREE.BO": "WAAREE.NS",
    "SUZLON": "SUZLON.NS",
    "SUZLON.NS": "SUZLON.NS",
    "SUZLON.BO": "SUZLON.NS",
    "OLECTRA": "OLECTRA.NS",
    "OLECTRA.NS": "OLECTRA.NS",
    "OLECTRA.BO": "OLECTRA.NS",
    "JNKINDIA": "JNKINDIA.NS",
    "JNKINDIA.NS": "JNKINDIA.NS",
    "JNKINDIA.BO": "JNKINDIA.NS",
    "GHVINFRA": "GHVINFRA.NS",
    "GHVINFRA.NS": "GHVINFRA.NS",
    "GHVINFRA.BO": "GHVINFRA.BO",
    "DIXON": "DIXON.NS",
    "DIXON.NS": "DIXON.NS",
    "DIXON.BO": "DIXON.NS",
    "KAYNES": "KAYNES.NS",
    "KAYNES.NS": "KAYNES.NS",
    "KAYNES.BO": "KAYNES.NS",
    "NETWEB": "NETWEB.NS",
    "NETWEB.NS": "NETWEB.NS",
    "NETWEB.BO": "NETWEB.NS",
    "SYRMA": "SYRMA.NS",
    "SYRMA.NS": "SYRMA.NS",
    "SYRMA.BO": "SYRMA.NS",
    "OIL": "OIL.NS",
    "OIL.NS": "OIL.NS",
    "OIL.BO": "OIL.NS",
}


def _search_ticker_by_name(company_name: str) -> Optional[tuple]:
    """
    Search for a ticker by company name using yfinance search.
    Returns (ticker, Stock) if found, None if not.
    """
    import yfinance as yf

    try:
        # Use yfinance search endpoint
        search = yf.Search(company_name, max_results=5)

        if not search or not search.quotes:
            return None

        # Look for Indian stocks (.NS or .BO)
        for quote in search.quotes:
            symbol = quote.get("symbol", "")
            if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
                continue

            # Get full info
            ticker_data = yf.Ticker(symbol)
            info = ticker_data.info

            if not info or info.get("regularMarketPrice") is None:
                continue

            price = info.get("regularMarketPrice", 0)
            market_cap = info.get("marketCap", 0)
            volume = info.get("averageVolume", 0)
            name = info.get("longName", company_name)

            if price <= 0:
                continue

            builder = get_universe_builder()
            sector = builder._classify_sector(name, info.get("sector", ""), symbol)

            stock = Stock(
                ticker=symbol,
                name=name,
                sector=sector,
                price=price,
                market_cap_cr=round(market_cap / 1e7, 1) if market_cap else 0,
                avg_volume_lakh=round(volume * price / 1e5, 1) if volume and price else 0,
                last_updated=datetime.now().isoformat(),
                keywords=[],
                exchange="NSE" if symbol.endswith(".NS") else "BSE",
            )

            # Add to universe
            get_universe_builder().universe[symbol] = stock

            logger.info(f"Name search: '{company_name}' -> {symbol} = {name} | ₹{price:.2f} | {stock.market_cap_cr:.0f}Cr")
            return (symbol, stock)

    except Exception as e:
        logger.debug(f"Name search failed for '{company_name}': {e}")

    return None


def validate_ticker_on_the_fly(ticker: str, company_name: str = "") -> Optional[tuple]:
    """
    Validate a ticker not in the universe by fetching from yfinance.
    Returns (actual_ticker, Stock) if valid, None if not.
    Caches results to avoid repeated yfinance calls.
    """
    if ticker in _dynamic_cache:
        return _dynamic_cache[ticker]

    # Step 1: Check known ticker map first (fast, no API call)
    normalized = ticker.replace(".NS", "").replace(".BO", "").upper()
    if normalized in _KNOWN_TICKER_MAP:
        mapped_ticker = _KNOWN_TICKER_MAP[normalized]
        # Check if mapped ticker is in universe
        if mapped_ticker in get_universe_builder().universe:
            stock = get_universe_builder().universe[mapped_ticker]
            logger.info(f"Known ticker map: {ticker} -> {mapped_ticker} ({stock.name})")
            result = (mapped_ticker, stock)
            _dynamic_cache[ticker] = result
            return result
        else:
            # Mapped ticker not in universe — try to fetch it from yfinance
            try:
                stock_data = yf.Ticker(mapped_ticker)
                info = stock_data.info
                if info and info.get("regularMarketPrice"):
                    price = info.get("regularMarketPrice", 0)
                    market_cap = info.get("marketCap", 0)
                    volume = info.get("averageVolume", 0)
                    name = info.get("longName", normalized)
                    if price > 0:
                        builder = get_universe_builder()
                        sector = builder._classify_sector(name, info.get("sector", ""), mapped_ticker)
                        stock = Stock(
                            ticker=mapped_ticker,
                            name=name,
                            sector=sector,
                            price=price,
                            market_cap_cr=round(market_cap / 1e7, 1) if market_cap else 0,
                            avg_volume_lakh=round(volume * price / 1e5, 1) if volume and price else 0,
                            last_updated=datetime.now().isoformat(),
                            keywords=[],
                            exchange="NSE" if mapped_ticker.endswith(".NS") else "BSE",
                        )
                        get_universe_builder().universe[mapped_ticker] = stock
                        logger.info(f"Known ticker map + fetch: {ticker} -> {mapped_ticker} = {name} | ₹{price:.2f} | {stock.market_cap_cr:.0f}Cr")
                        result = (mapped_ticker, stock)
                        _dynamic_cache[ticker] = result
                        return result
            except Exception as e:
                logger.debug(f"Known ticker map fetch failed for {mapped_ticker}: {e}")

    # Step 2: Try yfinance with NSE then BSE
    base = ticker.replace(".NS", "").replace(".BO", "")
    candidates = [f"{base}.NS", f"{base}.BO"]

    for t in candidates:
        try:
            stock_data = yf.Ticker(t)
            info = stock_data.info

            if not info or info.get("regularMarketPrice") is None:
                continue

            price = info.get("regularMarketPrice", 0)
            market_cap = info.get("marketCap", 0)
            volume = info.get("averageVolume", 0)
            name = info.get("longName", base)

            if price <= 0:
                continue

            builder = get_universe_builder()
            sector = builder._classify_sector(name, info.get("sector", ""), t)

            stock = Stock(
                ticker=t,
                name=name,
                sector=sector,
                price=price,
                market_cap_cr=round(market_cap / 1e7, 1) if market_cap else 0,
                avg_volume_lakh=round(volume * price / 1e5, 1) if volume and price else 0,
                last_updated=datetime.now().isoformat(),
                keywords=[],
                exchange="NSE" if t.endswith(".NS") else "BSE",
            )

            get_universe_builder().universe[t] = stock

            logger.info(f"Dynamic validation: {t} = {name} | ₹{price:.2f} | {stock.market_cap_cr:.0f}Cr")
            result = (t, stock)
            _dynamic_cache[ticker] = result
            return result

        except Exception as e:
            logger.debug(f"Dynamic validation failed for {t}: {e}")
            continue

    # Step 3: Try name-based search as last resort
    if company_name:
        result = _search_ticker_by_name(company_name)
        if result:
            _dynamic_cache[ticker] = result
            return result

    _dynamic_cache[ticker] = None
    return None