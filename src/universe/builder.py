"""
Dynamic Universe Builder
Pulls FULL small-cap list from Screener.in (no sector bias),
then validates via yfinance and tags with sector labels.

Flow: Screener.in discovery → yfinance validation → safety filter → sector tagging
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
UNIVERSE_CHANGE_LOG = DATA_DIR / "universe_changes.jsonl"
FULL_NSE_CACHE = DATA_DIR / "full_nse_stocks.json"
DYNAMIC_STOCKS_FILE = DATA_DIR / "dynamic_stocks.json"


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
    circuit_limit: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Stock":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def passes_stock_safety_filter(
    price: float,
    market_cap_cr: float,
    avg_volume_lakh: float = 0,
    avg_daily_value_cr: float = 0,
) -> bool:
    """
    Single safety filter used everywhere — universe build, on-the-fly validation, etc.
    Returns True if the stock passes ALL minimum safety checks.
    """
    from src.config import get_universe_config
    cfg = get_universe_config()

    price_min = cfg.get("price_min", 50)
    price_max = cfg.get("price_max", 500)
    cap_min = cfg.get("market_cap_min_cr", 100)
    cap_max = cfg.get("market_cap_max_cr", 5000)
    vol_min = cfg.get("min_avg_daily_volume_lakh", 50)
    value_min_cr = cfg.get("min_avg_daily_value_cr", 1.0)

    if not (price_min <= price <= price_max):
        return False
    if not (cap_min <= market_cap_cr <= cap_max):
        return False
    if avg_volume_lakh > 0 and avg_volume_lakh < vol_min:
        return False
    if avg_daily_value_cr > 0 and avg_daily_value_cr < value_min_cr:
        return False

    return True


def check_circuit_history(ticker: str, days: int = 30) -> dict:
    """
    Problem 8: Check if a stock has hit any circuits recently.
    Recent circuit hits count AGAINST a stock (hard to exit).
    Returns: {"has_circuit_hits": bool, "circuit_days": int, "max_lower_circuit_pct": float}
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=f"{days}d")
        if hist.empty or len(hist) < 2:
            return {"has_circuit_hits": False, "circuit_days": 0, "max_lower_circuit_pct": 0}

        circuit_days = 0
        max_lower_pct = 0

        for i in range(1, len(hist)):
            prev_close = float(hist["Close"].iloc[i - 1])
            curr_close = float(hist["Close"].iloc[i])
            if prev_close > 0:
                change_pct = abs((curr_close - prev_close) / prev_close * 100)
                # Indian markets have 5% or 10% circuit limits
                # A move of exactly 4.9-5.1% or 9.9-10.1% suggests circuit hit
                if (4.8 <= change_pct <= 5.2) or (9.8 <= change_pct <= 10.2) or change_pct >= 19.5:
                    circuit_days += 1
                    if curr_close < prev_close:
                        max_lower_pct = max(max_lower_pct, change_pct)

        return {
            "has_circuit_hits": circuit_days > 0,
            "circuit_days": circuit_days,
            "max_lower_circuit_pct": round(max_lower_pct, 2),
        }

    except Exception as e:
        logger.debug(f"Circuit check failed for {ticker}: {e}")
        return {"has_circuit_hits": False, "circuit_days": 0, "max_lower_circuit_pct": 0}


class UniverseBuilder:
    """
    Builds the tradeable stock universe.
    NEW flow: Screener.in discovery (no sector bias) → yfinance validation → safety filter → sector tagging
    """

    def __init__(self):
        self.universe: Dict[str, Stock] = {}
        self.sector_keywords = get_all_sector_keywords()
        self.sector_tickers = get_all_sector_tickers()

    def build(self, force_refresh: bool = False) -> Dict[str, Stock]:
        """Build universe: Screener.in first, then validate, then tag sectors, then merge dynamic."""
        if not force_refresh and self._load_cache():
            # Merge dynamic stocks into cached universe
            dynamic = self._load_dynamic_stocks()
            for k, v in dynamic.items():
                if k not in self.universe:
                    self.universe[k] = v
            logger.info(f"Loaded {len(self.universe)} stocks from cache + {len(dynamic)} dynamic")
            return self.universe

        logger.info("Building universe from scratch (Screener.in → yfinance → sector tagging)...")

        # 1. Discover ALL small-caps from Screener.in (no sector bias)
        screener_tickers = self._discover_from_screener()
        logger.info(f"Screener.in discovered {len(screener_tickers)} tickers")

        # 2. Add known sector tickers + NSE/BSE lookup/alias tickers (NOT as a gate)
        sector_ref_tickers = self._get_sector_reference_tickers()
        lookup_tickers = self._get_lookup_tickers()
        all_candidates = screener_tickers | sector_ref_tickers | lookup_tickers
        logger.info(
            f"Total candidates: {len(all_candidates)} "
            f"(screener {len(screener_tickers)} + sector ref {len(sector_ref_tickers)} + lookup {len(lookup_tickers)})"
        )

        # 3. Validate via yfinance (price, market cap, volume)
        validated = self._validate_tickers(all_candidates)

        # 4. Apply safety filter (single function used everywhere)
        filtered = {}
        for ticker, stock in validated.items():
            if passes_stock_safety_filter(stock.price, stock.market_cap_cr, stock.avg_volume_lakh):
                filtered[ticker] = stock
            else:
                logger.debug(f"Filtered out: {ticker} ({stock.name}) — price={stock.price}, cap={stock.market_cap_cr}Cr")

        # 5. Tag sectors (label added AFTER filtering, not before)
        self._tag_sectors(filtered)

        # 6. Enrich with keywords
        self._enrich_keywords(filtered)

        # 7. Merge any previously discovered dynamic stocks
        dynamic = self._load_dynamic_stocks()
        for k, v in dynamic.items():
            if k not in filtered:
                filtered[k] = v

        # 8. Save
        self.universe = filtered
        self._save_cache()

        logger.info(f"Universe built: {len(self.universe)} tradeable stocks ({len(dynamic)} dynamic)")
        return self.universe

    def _get_sector_reference_tickers(self) -> Set[str]:
        """Get sector tickers as a reference pool (not a gate). These get validated like everything else."""
        tickers = set()
        for sector_tickers in self.sector_tickers.values():
            for t in sector_tickers:
                if not t.endswith(".NS") and not t.endswith(".BO"):
                    tickers.add(t + ".NS")
                    tickers.add(t + ".BO")
                else:
                    tickers.add(t)
        return tickers

    def _get_lookup_tickers(self) -> Set[str]:
        """All tickers referenced in the NSE/BSE lookup JSON + ticker aliases.
        Ensures any company name that appears in news gets validated into the universe."""
        tickers = set()
        try:
            import json
            from src.universe.ticker_map import TICKER_ALIASES

            path = Path(__file__).parent.parent.parent / "config" / "nse_bse_tickers.json"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for v in data.get("lookup", {}).values():
                if isinstance(v, str) and v:
                    tickers.add(v)
            for v in TICKER_ALIASES.values():
                if isinstance(v, str) and v:
                    tickers.add(v)
        except Exception as e:
            logger.warning(f"Failed to load lookup tickers: {e}")
        return tickers

    def _discover_from_screener(self) -> Set[str]:
        """
        Discover small-cap stocks from Screener.in using fundamental filters.
        No sector bias — just price, market cap, and volume.
        """
        discovered = set()

        # Multiple queries to cast a wide net (matches loosened universe filters)
        queries = [
            "marketcap:50to50000+price:20to1000",
            "marketcap:50to50000+volume:>1000000",
            "price:20to200+marketcap:50to5000",
            "price:200to1000+marketcap:500to50000",
            "current_ratio:>1.5+price:20to1000+marketcap:50to50000",
            "roe:>+15+price:20to1000+marketcap:50to50000",
            "profit_margin:>+10+price:20to1000+marketcap:50to50000",
            "debt_to_equity:<1+price:20to1000+marketcap:50to50000",
        ]

        for query in queries:
            try:
                url = f"https://www.screener.in/screens/?q={query}"
                resp = requests.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.debug(f"Screener query '{query}' returned {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, "lxml")

                for row in soup.select("table.data-table tr"):
                    link = row.select_one("td a[href*='/company/']")
                    if link:
                        ticker = link["href"].split("/")[-1].upper()
                        if "." not in ticker:
                            ticker = f"{ticker}.NS"
                        discovered.add(ticker)

                time.sleep(1.5)  # Rate limit

            except Exception as e:
                logger.warning(f"Screener discovery failed for '{query}': {e}")

        logger.info(f"Screener.in discovered {len(discovered)} unique tickers")
        return discovered

    def _validate_tickers(self, tickers: Set[str]) -> Dict[str, Stock]:
        """Fetch and validate fundamental data via yfinance, with NSE→BSE fallback."""
        validated = {}

        # Separate into NSE and BSE tickers
        nse_tickers = {t for t in tickers if t.endswith(".NS")}
        bse_tickers = {t for t in tickers if t.endswith(".BO")}

        # Group by base ticker
        base_to_nse = {t.replace(".NS", ""): t for t in nse_tickers}
        base_to_bse = {t.replace(".BO", ""): t for t in bse_tickers}

        all_bases = set(base_to_nse.keys()) | set(base_to_bse.keys())

        # Batch process in chunks
        chunk_size = 50
        base_list = list(all_bases)

        for i in range(0, len(base_list), chunk_size):
            chunk_bases = base_list[i : i + chunk_size]
            self._fetch_chunk_with_fallback(chunk_bases, base_to_nse, base_to_bse, validated)
            time.sleep(0.5)

        return validated

    def _fetch_chunk_with_fallback(
        self,
        bases: List[str],
        base_to_nse: Dict,
        base_to_bse: Dict,
        out: Dict[str, Stock],
    ):
        """Fetch chunk with NSE→BSE fallback."""
        to_try = []
        for base in bases:
            if base in base_to_nse:
                to_try.append((base, base_to_nse[base], "NSE"))
            elif base in base_to_bse:
                to_try.append((base, base_to_bse[base], "BSE"))

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
                avg_vol_lakh = round(volume * price / 1e5, 1) if volume and price else 0

                # Raw data — safety filter applied later
                if price <= 0:
                    continue

                sector = self._classify_sector(
                    info.get("longName", ""), info.get("sector", ""), ticker
                )

                out[ticker] = Stock(
                    ticker=ticker,
                    name=info.get("longName", ticker),
                    sector=sector,  # Will be re-tagged later
                    price=price,
                    market_cap_cr=round(market_cap / 1e7, 1) if market_cap else 0,
                    avg_volume_lakh=avg_vol_lakh,
                    last_updated=datetime.now().isoformat(),
                    keywords=[],
                    exchange=exchange,
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
                            avg_vol_lakh = round(volume * price / 1e5, 1) if volume and price else 0

                            if price <= 0:
                                continue

                            sector = self._classify_sector(
                                info.get("longName", ""), info.get("sector", "")
                            )
                            out[ticker] = Stock(
                                ticker=ticker,
                                name=info.get("longName", ticker),
                                sector=sector,
                                price=price,
                                market_cap_cr=round(market_cap / 1e7, 1) if market_cap else 0,
                                avg_volume_lakh=avg_vol_lakh,
                                last_updated=datetime.now().isoformat(),
                                keywords=[],
                                exchange="BSE",
                            )
                        except Exception:
                            pass
                except Exception:
                    pass

    def _classify_sector(self, name: str, yf_sector: str, ticker: str = "") -> str:
        """Classify stock into our sectors (initial classification, may be overridden by _tag_sectors)"""
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

    def _tag_sectors(self, stocks: Dict[str, Stock]):
        """
        Tag each stock with a sector label AFTER filtering.
        Uses: (1) known sector tickers, (2) yfinance sector, (3) name/keyword matching.
        Sector becomes a label, not a gate.
        """
        # Build reverse map: ticker → sector from config
        config_sector_map = {}
        for sector, tickers in self.sector_tickers.items():
            for t in tickers:
                base = t.replace(".NS", "").replace(".BO", "")
                config_sector_map[base.upper()] = sector
                config_sector_map[f"{base}.NS"] = sector

        for ticker, stock in stocks.items():
            base = ticker.replace(".NS", "").replace(".BO", "")

            # Priority 1: config sector mapping
            if base in config_sector_map:
                stock.sector = config_sector_map[base]
                continue

            # Priority 2: name + yfinance sector keyword matching
            text = (stock.name + " " + stock.sector).lower()
            best_sector = "other"
            best_score = 0
            for sector, keywords in self.sector_keywords.items():
                score = sum(1 for kw in keywords if kw.lower() in text)
                if score > best_score:
                    best_score = score
                    best_sector = sector
            if best_score > 0:
                stock.sector = best_sector

    def _log_changes(self, new_stocks: set, rejected: list):
        """Log universe changes for bias detection."""
        try:
            UNIVERSE_CHANGE_LOG.parent.mkdir(exist_ok=True)
            entry = {
                "timestamp": datetime.now().isoformat(),
                "passed_count": len(new_stocks),
                "rejected_count": len(rejected),
                "rejected_samples": [{"ticker": t, "name": n, "reason": r} for t, n, r in rejected[:10]],
            }
            with open(UNIVERSE_CHANGE_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.debug(f"Failed to log universe changes: {e}")

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

    def _load_dynamic_stocks(self) -> Dict[str, Stock]:
        """Load dynamically added stocks (discovered from news, persisted across runs)."""
        if not DYNAMIC_STOCKS_FILE.exists():
            return {}
        try:
            with open(DYNAMIC_STOCKS_FILE) as f:
                data = json.load(f)
            stocks = {}
            for k, v in data.get("stocks", {}).items():
                try:
                    stocks[k] = Stock.from_dict(v)
                except Exception:
                    pass
            logger.info(f"Loaded {len(stocks)} dynamic stocks from news discoveries")
            return stocks
        except Exception as e:
            logger.warning(f"Failed to load dynamic stocks: {e}")
            return {}

    def _save_dynamic_stocks(self):
        """Persist dynamically added stocks so they survive across runs."""
        dynamic = {}
        for k, v in self.universe.items():
            if v.last_updated and "dynamic_" in str(v.__dict__.get("source", "")):
                dynamic[k] = v.to_dict()
        # Also save any stock that was added via on-the-fly validation
        if not dynamic:
            # Save all stocks that weren't from the original screener build
            return
        try:
            DYNAMIC_STOCKS_FILE.parent.mkdir(exist_ok=True)
            data = {
                "updated_at": datetime.now().isoformat(),
                "stocks": dynamic,
            }
            with open(DYNAMIC_STOCKS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save dynamic stocks: {e}")

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
    Returns (ticker, Stock) if found and passes safety filter, None if not.
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
            avg_vol_lakh = round(volume * price / 1e5, 1) if volume and price else 0
            market_cap_cr = round(market_cap / 1e7, 1) if market_cap else 0

            if price <= 0:
                continue

            # Name sanity check: the search result must actually match the
            # requested company, not just a fuzzy lookalike (e.g. "Zen Technologies"
            # should NOT resolve to "Zensar Technologies").
            if not _name_matches(company_name, name):
                logger.debug(
                    f"Name search '{company_name}' -> {symbol} name mismatch ({name}), skipping"
                )
                continue

            # SAME safety filter as universe build (Problem 3)
            if not passes_stock_safety_filter(price, market_cap_cr, avg_vol_lakh):
                logger.debug(f"Name search '{company_name}' -> {symbol} failed safety filter (price={price}, cap={market_cap_cr}Cr)")
                continue

            builder = get_universe_builder()
            sector = builder._classify_sector(name, info.get("sector", ""), symbol)

            stock = Stock(
                ticker=symbol,
                name=name,
                sector=sector,
                price=price,
                market_cap_cr=market_cap_cr,
                avg_volume_lakh=avg_vol_lakh,
                last_updated=datetime.now().isoformat(),
                keywords=[],
                exchange="NSE" if symbol.endswith(".NS") else "BSE",
            )

            # Add to universe
            get_universe_builder().universe[symbol] = stock

            logger.info(f"Name search: '{company_name}' -> {symbol} = {name} | ₹{price:.2f} | {stock.market_cap_cr:.0f}Cr")
            # Persist dynamic addition
            try:
                get_universe_builder()._save_dynamic_stocks()
            except Exception:
                pass
            return (symbol, stock)

    except Exception as e:
        logger.debug(f"Name search failed for '{company_name}': {e}")

    return None


_NAME_STOP_TOKENS = {
    "ltd", "limited", "pvt", "private", "inc", "incorporated", "corporation",
    "corp", "group", "holdings", "company", "co", "india", "indian", "the",
    "technologies", "technology", "systems", "system", "industries", "industry",
    "international", "global", "enterprises", "enterprise", "limited",
}


def _name_tokens(name: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z]{3,}", name.lower())
    return [t for t in tokens if t not in _NAME_STOP_TOKENS]


def _name_matches(search_name: str, candidate_name: str) -> bool:
    """True if the searched company name plausibly matches the candidate name.
    Requires at least one distinctive token of the searched name to appear as a
    whole word in the candidate name. Falls back to True if no distinctive tokens."""
    tokens = _name_tokens(search_name)
    if not tokens:
        return True
    candidate = (candidate_name or "").lower()
    for tok in tokens:
        if re.search(r'\b' + re.escape(tok) + r'\b', candidate):
            return True
    return False


def validate_ticker_on_the_fly(ticker: str, company_name: str = "") -> Optional[tuple]:
    """
    Validate a ticker not in the universe by fetching from yfinance.
    Uses the SAME safety filter as universe build (Problem 3).
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
                    avg_vol_lakh = round(volume * price / 1e5, 1) if volume and price else 0
                    market_cap_cr = round(market_cap / 1e7, 1) if market_cap else 0

                    if price > 0 and passes_stock_safety_filter(price, market_cap_cr, avg_vol_lakh):
                        builder = get_universe_builder()
                        sector = builder._classify_sector(name, info.get("sector", ""), mapped_ticker)
                        stock = Stock(
                            ticker=mapped_ticker,
                            name=name,
                            sector=sector,
                            price=price,
                            market_cap_cr=market_cap_cr,
                            avg_volume_lakh=avg_vol_lakh,
                            last_updated=datetime.now().isoformat(),
                            keywords=[],
                            exchange="NSE" if mapped_ticker.endswith(".NS") else "BSE",
                        )
                        get_universe_builder().universe[mapped_ticker] = stock
                        logger.info(f"Known ticker map + fetch: {ticker} -> {mapped_ticker} = {name} | ₹{price:.2f} | {stock.market_cap_cr:.0f}Cr")
                        result = (mapped_ticker, stock)
                        _dynamic_cache[ticker] = result
                        # Persist dynamic addition
                        try:
                            get_universe_builder()._save_dynamic_stocks()
                        except Exception:
                            pass
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
            avg_vol_lakh = round(volume * price / 1e5, 1) if volume and price else 0
            market_cap_cr = round(market_cap / 1e7, 1) if market_cap else 0

            if price <= 0:
                continue

            # SAME safety filter as universe build (Problem 3)
            if not passes_stock_safety_filter(price, market_cap_cr, avg_vol_lakh):
                logger.debug(f"Dynamic validation {t} failed safety filter (price={price}, cap={market_cap_cr}Cr)")
                continue

            builder = get_universe_builder()
            sector = builder._classify_sector(name, info.get("sector", ""), t)

            stock = Stock(
                ticker=t,
                name=name,
                sector=sector,
                price=price,
                market_cap_cr=market_cap_cr,
                avg_volume_lakh=avg_vol_lakh,
                last_updated=datetime.now().isoformat(),
                keywords=[],
                exchange="NSE" if t.endswith(".NS") else "BSE",
            )

            get_universe_builder().universe[t] = stock

            logger.info(f"Dynamic validation: {t} = {name} | ₹{price:.2f} | {stock.market_cap_cr:.0f}Cr")
            result = (t, stock)
            _dynamic_cache[ticker] = result
            # Persist dynamic addition
            try:
                get_universe_builder()._save_dynamic_stocks()
            except Exception:
                pass
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


def save_dynamic_additions():
    """Persist any dynamically added stocks to disk."""
    try:
        builder = get_universe_builder()
        builder._save_dynamic_stocks()
    except Exception:
        pass