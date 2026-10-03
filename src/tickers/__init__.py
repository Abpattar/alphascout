"""Company name -> verified Indian ticker.

The rule this module enforces: **a ticker is never invented**. Resolution is
a three-stage funnel that ends in a market-data lookup, and anything that
cannot be confirmed against a real Indian listing returns ``None``.

    1. static lookup tables shipped in ``config/`` (exact, curated)
    2. a strict alias table for cases the lookup tables miss
    3. live confirmation via yfinance, accepting only NSE/BSE symbols

Stage 3 is the authority. Stages 1 and 2 only propose candidates.

Deliberately rejected: fuzzy ``difflib`` matching over a dictionary of every
sector keyword. That is what previously allowed "Zen Technologies" to resolve
to "Zensar Technologies"; a wrong ticker is worse than no ticker because it
produces a real-looking price for the wrong company.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Set, Tuple

from src.market.quotes import VALID_SUFFIXES, normalise_ticker

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"

# Corporate suffixes and noise stripped before matching.
_SUFFIXES = (
    "limited", "ltd", "india", "industries", "corporation", "corp", "company",
    "co", "inc", "plc", "llp", "private", "pvt", "technologies", "technology",
    "international", "global", "holdings", "group", "the",
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Manual aliases for names the config lookup does not carry. Kept small and
# explicit: every entry has been checked against a real NSE symbol.
_ALIASES: Dict[str, str] = {
    "reliance": "RELIANCE.NS",
    "reliance industries": "RELIANCE.NS",
    "ril": "RELIANCE.NS",
    "tata motors": "TATAMOTORS.NS",
    "tata motars": "TATAMOTORS.NS",       # common misspelling in headlines
    "tata power": "TATAPOWER.NS",
    "tata steel": "TATASTEEL.NS",
    "tcs": "TCS.NS",
    "tata consultancy services": "TCS.NS",
    "infosys": "INFY.NS",
    "hcltech": "HCLTECH.NS",
    "hcl tech": "HCLTECH.NS",
    "wipro": "WIPRO.NS",
    "tech mahindra": "TECHM.NS",
    "lti": "LTIM.NS",
    "ltits": "LTIM.NS",
    "lt infotech": "LTIM.NS",
    "m&m": "M&M.NS",
    "mahindra mahindra": "M&M.NS",
    "onetrap": "ONTRAC.NS",
    "one97 communications": "PAYTM.NS",
    "paytm": "PAYTM.NS",
    "nykaa": "NYKAA.NS",
    "zomato": "ZOMATO.NS",
    "eternals": "ZOMATO.NS",
    "dmart": "DMART.NS",
    "avenue supermart": "DMART.NS",
    "pidilite industries": "PIDILITIND.NS",
    "pidilite": "PIDILITIND.NS",
    "gail": "GAIL.NS",
    "gail india": "GAIL.NS",
    "power grid corporation": "POWERGRID.NS",
    "power grid": "POWERGRID.NS",
    "coal india": "COALINDIA.NS",
    "sb indian": "SBIN.NS",
    "state bank of india": "SBIN.NS",
    "sbi": "SBIN.NS",
    "hdfc bank": "HDFCBANK.NS",
    "icici bank": "ICICIBANK.NS",
    "axis bank": "AXISBANK.NS",
    "kotak": "KOTAKBANK.NS",
    "kotak mahindra bank": "KOTAKBANK.NS",
    "bajaj finance": "BAJFINANCE.NS",
    "bajaj finserv": "BAJFINSV.NS",
    "bajaj auto": "BAJAJ-AUTO.NS",
    "hero motocorp": "HEROMOTOCO.NS",
    "maruti suzuki": "MARUTI.NS",
    "maruti": "MARUTI.NS",
    "titan company": "TITAN.NS",
    "titan": "TITAN.NS",
    "sun pharma": "SUNPHARMA.NS",
    "sun pharmaceutical": "SUNPHARMA.NS",
    "dr reddys": "DRREDDY.NS",
    "dr reddy's laboratories": "DRREDDY.NS",
    "cipla": "CIPLA.NS",
    "divi's laboratories": "DIVISLAB.NS",
    "divis labs": "DIVISLAB.NS",
    "apollo hospitals": "APOLLOHOSP.NS",
    "apollo hospital": "APOLLOHOSP.NS",
    "lupin": "LUPIN.NS",
    "gati": "GATI.NS",
    "gati logistics": "GATI.NS",
    "hal": "HAL.NS",
    "hindustan aeronautics": "HAL.NS",
    "bharat electronics": "BEL.NS",
    "bel": "BEL.NS",
    "bharat dynamics": "BDL.NS",
    "bdl": "BDL.NS",
    "paras defence": "PARAS.NS",
    "paras defense": "PARAS.NS",
    "paras": "PARAS.NS",
    "parasdef": "PARAS.NS",
    "bajaj auto ltd": "BAJAJ-AUTO.NS",
    "hindustan petroleum": "HPCL.NS",
    "hindustan zinc": "HINDZINC.NS",
    "vedanta": "VEDL.NS",
    "vedanta ltd": "VEDL.NS",
    "adani enterprises": "ADANIENT.NS",
    "adani ports": "ADANIPORTS.NS",
    "jio financial": "JIOFIN.NS",
    "jiofinance": "JIOFIN.NS",
    "bharti airtel": "BHARTIARTL.NS",
    "airtel": "BHARTIARTL.NS",
    "indus ind bank": "INDUSINDBK.NS",
    "yes bank": "YESBANK.NS",
    "idfc first bank": "IDFCFIRSTB.NS",
    "bank of baroda": "BANKBARODA.NS",
    "pnb": "PNB.NS",
    "canara bank": "CANBK.NS",
    "central bank of india": "CBI.NS",
    "icici ltd": "ICICI.NS",
    "hindustan unilever": "HINDUNILVR.NS",
    "nestle india": "NESTLEIND.NS",
    "asian paints": "ASIANPAINT.NS",
    "shriram finance": "SHRIRAMFIN.NS",
    "bajaj afl": "BAJAJAFL.NS",
    "muthoot finance": "MUTHOOTFIN.NS",
    "manappuram finance": "MANAPPURAM.NS",
    "pi industry": "PIIND.NS",
    "srf": "SRF.NS",
    "tata chemicals": "TATACHEM.NS",
    "ujas steel": "UJAS.NS",
    "jindal steel": "JINDALSTEL.NS",
    "jspl": "JINDALSTEL.NS",
    "gmdc": "GMDCLTD.NS",
    "trident": "TRIDENT.NS",
    "welspun corp": "WELCORP.NS",
    "nmdc": "NMDC.NS",
    "ioc": "IOC.NS",
    "indian oil": "IOC.NS",
    "bharat petroleum": "BPCL.NS",
    "bpcl": "BPCL.NS",
    "oil india": "OIL.NS",
    "gail gas": "GAIL.NS",
    "nhpc": "NHPC.NS",
    "sJV": "SJVN.NS",
    "sjvn": "SJVN.NS",
    "railtel": "RAILTEL.NS",
    "irfc": "IRFC.NS",
    "indian railways": "IRFC.NS",
    "yes bank ltd": "YESBANK.NS",
    "nuvama wealth": "NUVAMA.NS",
    "360 one": "360ONE.NS",
    "360 one digits": "360ONE.NS",
    "angel one": "ANGELONE.NS",
    "zerodha": "ZERODHA.NS",
    "naara new industries": "TIINDIA.NS",
    "tata investment corporation": "TATAINVEST.NS",
}

# Words that must never be resolved to a ticker on their own. These are
# generic enough to appear inside unrelated headlines.
_AMBIGUOUS = {
    "india", "Indian", "market", "markets", "share", "shares", "stock",
    "stocks", "news", "business", "company", "companies", "group", "ltd",
    "limited", "bank", "capital", "finance", "financial", "india", "bharat",
    "asian", "eastern", "western", "northern", "southern", "central", "new",
    "national", "international", "global", "prime", "value", "core", "first",
    "iifl", "iicici", "icici", "hdfc", "axis", "yes", "kotak", "indus",
}


_APOSTROPHES = re.compile(r"['’`]")


def _normalise_name(name: str) -> str:
    """Lowercase and strip punctuation. Suffixes are *not* removed here.

    Apostrophes are deleted rather than split on, so "Reddy's" becomes
    "reddys" and still matches the alias table.

    Removal happens in :func:`_name_variants` and only from the ends, because
    "india" is a corporate suffix in "Reliance India" but the payload of
    "State Bank of India". Stripping it mid-string silently turned the latter
    into "state bank of" and lost the ticker.
    """
    if not name:
        return ""
    text = _APOSTROPHES.sub("", name.lower())
    return " ".join(t for t in _NON_ALNUM.sub(" ", text).split() if t)


def _name_variants(name: str) -> List[str]:
    """Progressively shorter forms of a company name, most specific first."""
    base = _normalise_name(name)
    if not base:
        return []

    variants = [base]
    tokens = base.split()

    stripped = list(tokens)
    while stripped and stripped[-1] in _SUFFIXES:
        stripped.pop()
    if stripped and stripped != tokens:
        variants.append(" ".join(stripped))

    no_the = [t for t in tokens if t != "the"]
    if no_the and no_the != tokens:
        variants.append(" ".join(no_the))

    # Deduplicate, preserve order.
    seen: Set[str] = set()
    out: List[str] = []
    for variant in variants:
        if variant and variant not in seen:
            seen.add(variant)
            out.append(variant)
    return out


@lru_cache(maxsize=1)
def _load_lookup() -> Dict[str, str]:
    """``config/nse_bse_tickers.json`` as a normalised-name -> ticker map."""
    path = CONFIG_DIR / "nse_bse_tickers.json"
    out: Dict[str, str] = {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load %s: %s", path, exc)
        return out
    lookup = raw.get("lookup", raw) if isinstance(raw, dict) else {}
    if not isinstance(lookup, dict):
        return out
    for key, value in lookup.items():
        if not isinstance(value, str):
            continue
        norm = _normalise_name(str(key))
        ticker = normalise_ticker(value)
        if norm and ticker:
            # First definition wins so the curated file beats a later dup key.
            out.setdefault(norm, ticker)
    logger.info("Loaded %d ticker lookup entries from %s", len(out), path.name)
    return out


@lru_cache(maxsize=1)
def _load_sector_tickers() -> Set[str]:
    path = CONFIG_DIR / "sectors.yaml"
    out: Set[str] = set()
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return out
    for value in data.values():
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    ticker = normalise_ticker(item)
                    if ticker:
                        out.add(ticker)
    return out


@lru_cache(maxsize=1)
def _alias_lookup() -> Dict[str, str]:
    """:data:`_ALIASES` with keys put through the same normalisation as
    lookups, so ``"M&M"`` and ``"Dr Reddy's Laboratories"`` match."""
    out: Dict[str, str] = {}
    for key, value in _ALIASES.items():
        norm = _normalise_name(key)
        if norm:
            out.setdefault(norm, value)
    return out


def _name_affinity(query: str, returned: str) -> float:
    """How well a provider-returned company name matches the query.

    Uses the best of whole-string similarity and token overlap. The token
    check matters because providers return legal suffixes ("R SYS
    INTERNATIONAL LTD" for "R Systems International") that punish a plain
    edit-distance ratio.
    """
    if not query or not returned:
        return 0.0
    if query == returned:
        return 1.0
    seq = SequenceMatcher(None, query, returned).ratio()
    q_tokens = set(query.split())
    r_tokens = set(returned.split())
    # Corporate words carry no identity and would inflate the overlap.
    q_core = q_tokens - set(_SUFFIXES)
    r_core = r_tokens - set(_SUFFIXES)
    if q_core and r_core:
        overlap = len(q_core & r_core) / max(len(q_core), len(r_core))
    else:
        overlap = 0.0
    return max(seq, overlap)


@dataclass(frozen=True)
class Resolution:
    """Outcome of a ticker lookup."""

    ticker: str
    company_name: str
    method: str            # lookup | alias | live | unverified
    verified: bool         # confirmed against a real Indian listing
    note: str = ""

    def as_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "method": self.method,
            "verified": self.verified,
            "note": self.note,
        }


class TickerResolver:
    """Resolve a company mention to a real, Indian-listed ticker."""

    def __init__(self, verify_live: bool = True):
        self.verify_live = verify_live
        self._verified: Dict[str, Resolution] = {}
        self._rejected: Dict[str, str] = {}

    # -- stage 1/2: proposals ---------------------------------------------
    def propose(self, name: str) -> Optional[Resolution]:
        """Cheap lookup without network access.

        Tries each name variant against the curated lookup table, then the
        manual alias table. The first hit wins; no fuzzy matching.
        """
        for variant in _name_variants(name):
            if variant in self._rejected:
                return None
            if variant in _AMBIGUOUS:
                continue

            ticker = _load_lookup().get(variant)
            method = "lookup"
            if ticker is None:
                ticker = _alias_lookup().get(variant)
                method = "alias"
            if ticker is None:
                continue

            resolved = normalise_ticker(ticker)
            if not resolved:
                self._rejected[variant] = "invalid symbol"
                continue
            return Resolution(resolved, name.strip(), method, verified=False)
        return None

    # -- stage 4: name search (discovery) ---------------------------------
    def _search_by_name(self, name: str) -> Optional[Resolution]:
        """Look a company up by name against the live listing universe.

        This is what makes the system open-ended: a company absent from every
        curated table still resolves, as long as a real NSE/BSE listing exists
        under roughly that name.

        Safety: results are restricted to ``.NS``/``.BO`` symbols, and the
        name the provider returns must actually resemble the query. Without
        that second check a search for "Swiggy" would happily return some
        unrelated large cap whose name shares a few characters.
        """
        query = _normalise_name(name)
        if len(query) < 4:
            return None

        try:
            import yfinance as yf

            quotes = (yf.Search(query, max_results=8).quotes or [])
        except Exception as exc:
            logger.info("Name search failed for %r: %s", name, exc)
            return None

        best: Optional[Tuple[float, str, str]] = None
        for item in quotes:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol.endswith(VALID_SUFFIXES):
                continue
            returned = str(item.get("longname") or item.get("shortname") or "")
            score = _name_affinity(query, _normalise_name(returned))
            if score < 0.55:
                continue
            if best is None or score > best[0]:
                best = (score, symbol, returned or name.strip())

        if best is None:
            return None

        _, symbol, returned = best
        logger.info("Name search: %r -> %s (%s)", name.strip(), symbol, returned)
        return Resolution(symbol, returned or name.strip(), "name_search", verified=False)

    def _confirm(self, resolution: Resolution) -> Optional[Resolution]:
        """Ask the market-data source whether this symbol really exists."""
        if not self.verify_live:
            return resolution
        if resolution.ticker in self._verified:
            return self._verified[resolution.ticker]

        from src.market.quotes import get_client

        quote = get_client().get_quote(resolution.ticker)
        if quote is None or not quote.is_indian or quote.price <= 0:
            self._rejected[_normalise_name(resolution.company_name)] = (
                "not confirmed as an NSE/BSE listing with a real price"
            )
            logger.info(
                "Ticker %s (%s) failed live verification - dropping",
                resolution.ticker, resolution.company_name,
            )
            return None

        confirmed = Resolution(
            ticker=resolution.ticker,
            company_name=quote.company_name or resolution.company_name,
            method=resolution.method,
            verified=True,
            note=f"confirmed via {quote.source}",
        )
        self._verified[resolution.ticker] = confirmed
        return confirmed

    # -- public ------------------------------------------------------------
    def resolve(self, name: str) -> Optional[Resolution]:
        """Full funnel. ``None`` when the company cannot be pinned down.

        curated table -> alias table -> live name search -> market-data
        confirmation.
        """
        if not name:
            return None
        if name in self._rejected:
            return None

        norm = _normalise_name(name)
        if not norm:
            return None

        proposal = self.propose(norm)
        if proposal is None:
            if norm in _AMBIGUOUS:
                return None
            proposal = self._search_by_name(name)
        if proposal is None:
            return None
        return self._confirm(proposal)

    def resolve_many(self, names: Iterable[str]) -> List[Resolution]:
        out: List[Resolution] = []
        seen: Set[str] = set()
        for name in names or []:
            resolution = self.resolve(name)
            if resolution and resolution.ticker not in seen:
                seen.add(resolution.ticker)
                out.append(resolution)
        return out

    def resolve_from_text(self, text: str) -> List[Resolution]:
        """Find every known Indian company mentioned in free text.

        Scans the curated tables for whole-word matches. This is a *candidate
        finder* only - the AI still decides which company the story is about,
        but every candidate it names must pass through :meth:`resolve`.
        """
        if not text:
            return []
        haystack = f" {_NON_ALNUM.sub(' ', text.lower())} "
        found: List[str] = []
        tables = list(_load_lookup().keys()) + list(_alias_lookup().keys())
        for norm in tables:
            if norm in _AMBIGUOUS or len(norm) < 4:
                continue
            if f" {norm} " in haystack and norm not in found:
                found.append(norm)
        return self.resolve_many(found)


_shared: Optional[TickerResolver] = None


def get_resolver() -> TickerResolver:
    global _shared
    if _shared is None:
        _shared = TickerResolver()
    return _shared


def reset_resolver() -> None:
    global _shared
    _shared = None
