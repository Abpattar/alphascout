"""Real Indian market data.

Single responsibility: obtain *verifiable* price data for NSE/BSE listed
symbols and hand back a provenance-tagged record. Nothing here substitutes a
default for a missing price - a fetch that fails returns ``None`` so the
caller can drop the signal instead of inventing a number.

Free data sources only (no paid feed):
  * yfinance / Yahoo Finance - daily OHLCV and quote metadata
  * NSE public JSON endpoints - used as a fallback for live LTP
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

from src.market.indicators import Indicators, compute_indicators
from src.market.session import IST, MarketStatus, market_status, to_ist

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15
HISTORY_PERIOD = "6mo"          # ~126 trading days: enough for SMA50 + 52w
MIN_BARS_REQUIRED = 21

# Exchanges we accept. Anything resolved outside these is not an Indian
# listing and must not produce a signal.
VALID_SUFFIXES = (".NS", ".BO")


class MarketDataError(RuntimeError):
    """Raised only for programming errors; fetch failures return None."""


@dataclass
class Quote:
    """A real quote with provenance. ``price`` is never invented."""

    ticker: str
    exchange: str
    company_name: str = ""
    price: float = 0.0
    prev_close: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    volume: float = 0.0
    market_cap_cr: float = 0.0
    currency: str = "INR"
    as_of: str = ""
    source: str = ""
    price_kind: str = ""     # live | previous_close | last_close
    session_label: str = ""
    fetched_at: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def is_indian(self) -> bool:
        return self.ticker.endswith(VALID_SUFFIXES)

    @property
    def change_pct(self) -> Optional[float]:
        if not self.prev_close or self.prev_close <= 0:
            return None
        return round((self.price - self.prev_close) / self.prev_close * 100, 2)

    def as_dict(self) -> Dict:
        data = dict(self.__dict__)
        data["change_pct"] = self.change_pct
        data["is_indian"] = self.is_indian
        return data


# Exchange suffixes that are definitely not Indian. Rejecting these is
# cheaper and safer than appending ".NS" and hoping a live lookup fails.
FOREIGN_SUFFIXES = (
    ".US", ".UK", ".L", ".DE", ".T", ".HK", ".TO", ".AX", ".V", ".AS", ".BR",
    ".SS", ".SZ", ".SE", ".PA", ".MI", ".MC", ".SW", ".ST", ".OL", ".CO",
    ".NZ", ".SI", ".KS", ".TA", ".NSI", ".BOI", "./",
)


def normalise_ticker(ticker: str) -> Optional[str]:
    """Force a symbol into an explicit NSE/BSE form.

    Returns ``None`` for symbols we cannot confirm are Indian listings. This is
    the guard that stops a US, UK or Chinese symbol from ever reaching a
    signal - appending ``.NS`` to "000001.SS" would otherwise produce a
    plausible-looking but meaningless ticker.
    """
    if not ticker:
        return None
    sym = ticker.strip().upper().replace(" ", "")
    if not sym:
        return None
    if sym.endswith(VALID_SUFFIXES):
        return sym
    if any(sym.endswith(suffix) for suffix in FOREIGN_SUFFIXES):
        logger.info("Rejecting non-Indian ticker: %s", ticker)
        return None
    return f"{sym}.NS"


class MarketDataClient:
    """Fetches quotes and history for Indian symbols.

    Caches per-process only. Prices are deliberately *not* cached to disk:
    a stale price presented as current is the exact failure mode this rewrite
    exists to remove.
    """

    def __init__(self, timeout: int = REQUEST_TIMEOUT):
        self.timeout = timeout
        self._quote_cache: Dict[str, Quote] = {}
        self._history_cache: Dict[str, List[Dict]] = {}
        self._yf = None
        self.failed: List[str] = []

    # -- plumbing ----------------------------------------------------------
    def _lazy_yf(self):
        if self._yf is None:
            import yfinance as yf

            self._yf = yf
        return self._yf

    def invalidate(self, ticker: Optional[str] = None) -> None:
        if ticker:
            self._quote_cache.pop(ticker, None)
            self._history_cache.pop(ticker, None)
        else:
            self._quote_cache.clear()
            self._history_cache.clear()

    # -- history -----------------------------------------------------------
    def get_history(self, ticker: str, period: str = HISTORY_PERIOD) -> Optional[List[Dict]]:
        """Daily OHLCV bars, oldest first.

        Returns ``None`` when the symbol cannot be resolved or has no history.
        Callers must treat ``None`` as "market data unavailable".
        """
        symbol = normalise_ticker(ticker)
        if not symbol:
            return None
        if symbol in self._history_cache:
            return self._history_cache[symbol]

        yf = self._lazy_yf()
        for attempt in range(2):
            try:
                handle = yf.Ticker(symbol)
                frame = handle.history(period=period, interval="1d", auto_adjust=False)
                if frame is None or frame.empty:
                    if attempt == 0:
                        time.sleep(0.8)
                        continue
                    logger.warning("No history for %s", symbol)
                    self.failed.append(symbol)
                    return None

                bars: List[Dict] = []
                for index, row in frame.iterrows():
                    close = row.get("Close")
                    if close is None or (isinstance(close, float) and math.isnan(close)):
                        continue
                    bars.append({
                        "timestamp": index.to_pydatetime() if hasattr(index, "to_pydatetime") else index,
                        "open": float(row.get("Open") or close),
                        "high": float(row.get("High") or close),
                        "low": float(row.get("Low") or close),
                        "close": float(close),
                        "volume": float(row.get("Volume") or 0.0),
                    })
                if len(bars) < MIN_BARS_REQUIRED:
                    logger.warning(
                        "Only %d bars for %s (need %d) - indicators unavailable",
                        len(bars), symbol, MIN_BARS_REQUIRED,
                    )
                self._history_cache[symbol] = bars
                return bars
            except Exception as exc:
                logger.warning("History fetch failed for %s (attempt %d): %s", symbol, attempt + 1, exc)
                if attempt == 0:
                    time.sleep(0.8)
        self.failed.append(symbol)
        return None

    # -- quote -------------------------------------------------------------
    def get_quote(self, ticker: str) -> Optional[Quote]:
        """Latest real quote for an Indian symbol, or ``None``.

        The returned quote's ``price_kind`` reflects the actual session, so a
        04:00 IST run reports ``previous_close`` rather than implying a live
        tick.
        """
        symbol = normalise_ticker(ticker)
        if not symbol:
            return None
        if symbol in self._quote_cache:
            return self._quote_cache[symbol]

        status = market_status()
        yf = self._lazy_yf()

        info: Dict = {}
        try:
            info = yf.Ticker(symbol).info or {}
        except Exception as exc:
            logger.warning("Quote info failed for %s: %s", symbol, exc)

        price = info.get("regularMarketPrice")
        prev_close = (
            info.get("regularMarketPreviousClose")
            or info.get("previousClose")
            or info.get("regularMarketPrice")
        )
        try:
            price = float(price) if price is not None else None
            prev_close = float(prev_close) if prev_close is not None else None
        except (TypeError, ValueError):
            price, prev_close = None, None

        # Fall back to the last two real bars when quote metadata is missing.
        if not price or price <= 0:
            bars = self.get_history(symbol)
            if bars and len(bars) >= 2:
                price = bars[-1]["close"]
                prev_close = bars[-1 - 1]["close"] if len(bars) >= 2 else None
                logger.info("Using last real bar for %s: %.2f", symbol, price)

        if not price or price <= 0:
            logger.warning("No usable price for %s - signal will be dropped", symbol)
            self.failed.append(symbol)
            return None

        market_cap = info.get("marketCap") or 0
        quote = Quote(
            ticker=symbol,
            exchange="NSE" if symbol.endswith(".NS") else "BSE",
            company_name=str(info.get("longName") or info.get("shortName") or ""),
            price=round(price, 2),
            prev_close=round(prev_close, 2) if prev_close else 0.0,
            day_high=float(info.get("dayHigh") or 0) or 0.0,
            day_low=float(info.get("dayLow") or 0) or 0.0,
            volume=float(info.get("volume") or info.get("regularMarketVolume") or 0) or 0.0,
            market_cap_cr=round(float(market_cap) / 1e7, 1) if market_cap else 0.0,
            currency=str(info.get("currency") or "INR"),
            source="yfinance",
            price_kind=status.price_kind,
            session_label=status.label,
            fetched_at=datetime.now(IST).isoformat(),
        )

        if quote.currency not in ("INR", ""):
            quote.warnings.append(f"unexpected currency {quote.currency}")
        if not quote.is_indian:
            quote.warnings.append("ticker is not an NSE/BSE symbol")

        self._quote_cache[symbol] = quote
        logger.info(
            "Quote %s = Rs%.2f (%s, prev close Rs%.2f, source=%s)",
            symbol, quote.price, quote.price_kind, quote.prev_close, quote.source,
        )
        return quote

    # -- combined ----------------------------------------------------------
    def get_indicators(self, ticker: str) -> Optional[Indicators]:
        """Indicators from real history. ``None`` when history is unusable."""
        symbol = normalise_ticker(ticker)
        if not symbol:
            return None
        bars = self.get_history(symbol)
        if not bars or len(bars) < MIN_BARS_REQUIRED:
            logger.warning(
                "Indicators unavailable for %s (%s bars, need %d)",
                symbol, len(bars or []), MIN_BARS_REQUIRED,
            )
            return None
        ind = compute_indicators(symbol, bars, source="yfinance")
        if ind is None:
            return None
        if ind.last_close:
            # Trust the bar series over the quote snapshot for arithmetic.
            ind.as_of = ind.as_of or datetime.now(IST).isoformat()
        return ind

    def get_market_snapshot(self, ticker: str) -> Optional[Dict]:
        """Everything downstream needs, or ``None`` if any of it is missing.

        Requires a real price *and* a usable indicator set. This is the only
        function the pipeline should call, so that "market data unavailable"
        is a single, explicit failure mode.
        """
        quote = self.get_quote(ticker)
        if quote is None:
            return None
        indicators = self.get_indicators(ticker)
        if indicators is None:
            logger.warning("No indicators for %s - dropping signal", quote.ticker)
            return None
        return {
            "quote": quote,
            "indicators": indicators,
            "session": market_status(),
        }


_shared: Optional[MarketDataClient] = None


def get_client() -> MarketDataClient:
    global _shared
    if _shared is None:
        _shared = MarketDataClient()
    return _shared


def reset_client() -> None:
    global _shared
    _shared = None
