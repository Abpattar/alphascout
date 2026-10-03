"""Indian market session logic.

All AlphaScout reasoning is anchored to IST and to the NSE/BSE trading
calendar, because the two production runs (04:00 and 07:00 IST) both happen
*before* the market opens. Getting this wrong is how a system ends up
presenting yesterday's close as a live quote.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30), "IST")

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PRE_OPEN = time(9, 0)

# Session identifiers used throughout the codebase and persisted in signals.
SESSION_OPEN = "OPEN"
SESSION_CLOSED = "CLOSED"
SESSION_PRE_OPEN = "PRE_OPEN"
SESSION_WEEKEND = "WEEKEND"
SESSION_HOLIDAY = "HOLIDAY"
SESSION_UNKNOWN = "UNKNOWN"

# Fallback NSE trading holidays. Only used when the live calendar cannot be
# fetched. Kept small and dated: a stale entry is harmless because a holiday
# that is actually a trading day only costs us a "previous close" label, while
# a missing entry would make us call a holiday's stale price live.
_FALLBACK_HOLIDAYS_2026 = {
    date(2026, 1, 26), date(2026, 3, 4), date(2026, 3, 21), date(2026, 3, 26),
    date(2026, 4, 1), date(2026, 4, 3), date(2026, 4, 14), date(2026, 5, 1),
    date(2026, 8, 15), date(2026, 10, 2), date(2026, 10, 21), date(2026, 11, 9),
    date(2026, 12, 25),
}


def now_ist() -> datetime:
    return datetime.now(IST)


def to_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


@dataclass(frozen=True)
class MarketStatus:
    """What the market is doing right now, and what 'current price' means."""

    session: str
    is_trading_day: bool
    as_of: datetime            # when the reference price is from
    price_kind: str            # live | previous_close | last_close
    label: str                 # human-readable, safe to show a user

    @property
    def is_live(self) -> bool:
        return self.price_kind == "live"


def _fetch_nse_holidays() -> Optional[set]:
    """Trading holidays from the NSE public API. ``None`` when unavailable."""
    try:
        import requests

        response = requests.get(
            "https://www.nseindia.com/api/holiday-master?type=trading",
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=8,
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("CM", [])
        holidays = set()
        for row in rows:
            raw = row.get("tradingDate") or row.get("trading_Date") or ""
            for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
                try:
                    holidays.add(datetime.strptime(raw.strip(), fmt).date())
                    break
                except (ValueError, AttributeError):
                    continue
        return holidays or None
    except Exception as exc:
        logger.debug("NSE holiday fetch failed: %s", exc)
        return None


_holiday_cache: dict = {}


def trading_holidays(year: Optional[int] = None) -> set:
    """NSE trading holidays for ``year``, cached per process.

    Falls back to a small hardcoded 2026 list rather than guessing, because
    "no holiday data" must never mean "the market is definitely open".
    """
    year = year or now_ist().year
    if year in _holiday_cache:
        return _holiday_cache[year]
    fetched = _fetch_nse_holidays()
    if fetched:
        holidays = {d for d in fetched if d.year == year}
    else:
        holidays = {d for d in _FALLBACK_HOLIDAYS_2026 if d.year == year}
        logger.info("Using fallback NSE holiday list for %s (%d dates)", year, len(holidays))
    _holiday_cache[year] = holidays
    return holidays


def is_trading_day(day: Optional[date] = None) -> bool:
    day = day or now_ist().date()
    if day.weekday() >= 5:
        return False
    return day not in trading_holidays(day.year)


def previous_trading_day(day: Optional[date] = None) -> date:
    """Most recent trading day strictly before ``day``."""
    day = day or now_ist().date()
    cursor = day - timedelta(days=1)
    for _ in range(30):
        if is_trading_day(cursor):
            return cursor
        cursor -= timedelta(days=1)
    return day - timedelta(days=1)


def market_status(at: Optional[datetime] = None) -> MarketStatus:
    """Classify the current market session.

    The returned ``price_kind`` is what every downstream label must respect:
    at 04:00 IST the honest answer is ``previous_close``, not ``live``.
    """
    at = to_ist(at or now_ist())
    today = at.date()
    clock = at.time()

    if today.weekday() >= 5:
        ref = previous_trading_day(today)
        return MarketStatus(
            SESSION_WEEKEND, False, at, "last_close",
            f"Weekend - last close from {ref:%d %b %Y}",
        )

    if not is_trading_day(today):
        ref = previous_trading_day(today)
        return MarketStatus(
            SESSION_HOLIDAY, False, at, "last_close",
            f"Market holiday - last close from {ref:%d %b %Y}",
        )

    if clock < PRE_OPEN:
        ref = previous_trading_day(today)
        return MarketStatus(
            SESSION_CLOSED, True, at, "previous_close",
            f"Pre-open - previous close ({ref:%d %b %Y})",
        )

    if clock < MARKET_OPEN:
        return MarketStatus(
            SESSION_PRE_OPEN, True, at, "previous_close",
            "Pre-open session - previous close",
        )

    if clock <= MARKET_CLOSE:
        return MarketStatus(
            SESSION_OPEN, True, at, "live",
            f"Live - as of {at:%d %b %Y %H:%M} IST",
        )

    ref = today
    return MarketStatus(
        SESSION_CLOSED, True, at, "previous_close",
        f"Post-close - close of {ref:%d %b %Y}",
    )


def freshness_window_hours(default: int = 30) -> int:
    """How far back an article may be published and still count as new.

    Wide enough to survive a delayed GitHub cron (these have been observed
    firing hours late) and a weekend, narrow enough that a week-old article
    in a feed is not treated as news.
    """
    status = market_status()
    if status.session == SESSION_WEEKEND:
        return default + 48
    if status.session == SESSION_HOLIDAY:
        return default + 24
    return default
