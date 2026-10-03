"""Deterministic technical indicators and trade-level calculations.

Every function here is pure arithmetic over a real price series. Nothing in
this module invents a value: if the input series is too short, the caller
gets ``None`` and the signal is dropped rather than filled in.

Deliberately implemented from first principles rather than pulled from a
library so that every number in a Telegram message is traceable to a formula
visible in this file, and so the maths can be unit-tested without a network.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

IST = timezone(timedelta(hours=5, minutes=30), "IST")


@dataclass
class Indicators:
    """Technical state computed from a real OHLCV series."""

    ticker: str
    as_of: str = ""                 # ISO timestamp of the last bar
    bars: int = 0
    last_close: float = 0.0
    prev_close: float = 0.0
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    rsi_14: Optional[float] = None
    atr_14: Optional[float] = None
    support_20: Optional[float] = None
    resistance_20: Optional[float] = None
    volume: float = 0.0
    avg_volume_20: Optional[float] = None
    change_pct: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    source: str = ""
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "as_of": self.as_of,
            "bars": self.bars,
            "last_close": self.last_close,
            "prev_close": self.prev_close,
            "sma_20": self.sma_20,
            "sma_50": self.sma_50,
            "rsi_14": self.rsi_14,
            "atr_14": self.atr_14,
            "support_20": self.support_20,
            "resistance_20": self.resistance_20,
            "volume": self.volume,
            "avg_volume_20": self.avg_volume_20,
            "change_pct": self.change_pct,
            "high_52w": self.high_52w,
            "low_52w": self.low_52w,
            "source": self.source,
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def sma(values: Sequence[float], period: int) -> Optional[float]:
    """Simple moving average. ``None`` when there is not enough history."""
    if period <= 0 or len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / float(period)


def rsi(closes: Sequence[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI.

    Uses Wilder smoothing rather than a simple mean of gains/losses, which is
    the standard definition and what charting platforms report. Returns
    ``None`` with insufficient history instead of guessing.
    """
    if period <= 0 or len(closes) < period + 1:
        return None

    gains, losses = [], []
    for prev, cur in zip(closes[:-1], closes[1:]):
        delta = cur - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        # No downside in the window: RSI is by definition 100.
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def true_range(high: float, low: float, prev_close: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> Optional[float]:
    """Average True Range via Wilder smoothing."""
    if period <= 0 or len(closes) < period + 1:
        return None
    trs = [
        true_range(highs[i], lows[i], closes[i - 1])
        for i in range(1, len(closes))
    ]
    if len(trs) < period:
        return None
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = (value * (period - 1) + tr) / period
    return value


def swing_support_resistance(
    lows: Sequence[float],
    highs: Sequence[float],
    lookback: int = 20,
) -> tuple:
    """Support/resistance as the extremes of the recent swing.

    Explicitly defined rather than "whatever level looks right": support is
    the lowest low of the window, resistance the highest high. Documented here
    so the Telegram label can state the method.
    """
    if lookback <= 0 or len(lows) < 2 or len(highs) < 2:
        return None, None
    window = min(lookback, len(lows), len(highs))
    return min(lows[-window:]), max(highs[-window:])


# ---------------------------------------------------------------------------
# Indicator assembly
# ---------------------------------------------------------------------------

def compute_indicators(
    ticker: str,
    bars: Sequence[Dict],
    source: str = "",
) -> Optional[Indicators]:
    """Build :class:`Indicators` from OHLCV bars.

    ``bars`` must be chronological (oldest first) with ``open``/``high``/
    ``low``/``close``/``volume`` keys. Returns ``None`` when fewer than 21
    bars are available, because a 20-period average over 5 bars is not a
    moving average.

    Any individual indicator that lacks history stays ``None``; the object is
    still returned so a caller can report exactly which figures are available.
    """
    usable = [b for b in bars if b.get("close") is not None]
    if not usable:
        return None

    ind = Indicators(ticker=ticker, bars=len(usable), source=source)

    # Populate whatever the available bars genuinely support, even when the
    # series is too short for the longer indicators. Returning a stub with no
    # price would wrongly read as "no market data" when data plainly exists.
    closes_all = [float(b["close"]) for b in usable]
    ind.last_close = closes_all[-1]
    ind.prev_close = closes_all[-2] if len(closes_all) >= 2 else 0.0
    ind.volume = float(usable[-1].get("volume") or 0.0)
    if ind.prev_close:
        ind.change_pct = round((ind.last_close - ind.prev_close) / ind.prev_close * 100, 2)
    last_ts = usable[-1].get("timestamp") or usable[-1].get("date")
    if isinstance(last_ts, datetime):
        ind.as_of = last_ts.isoformat()
    elif last_ts:
        ind.as_of = str(last_ts)

    if len(usable) < 21:
        ind.notes.append(
            f"insufficient history: {len(usable)} bars, 21 needed for SMA20/RSI14"
        )
        return ind

    closes = closes_all
    highs = [float(b.get("high") or b["close"]) for b in usable]
    lows = [float(b.get("low") or b["close"]) for b in usable]
    volumes = [float(b.get("volume") or 0.0) for b in usable]

    ind.sma_20 = sma(closes, 20)
    ind.sma_50 = sma(closes, 50)
    ind.rsi_14 = rsi(closes, 14)
    ind.atr_14 = atr(highs, lows, closes, 14)
    ind.support_20, ind.resistance_20 = swing_support_resistance(lows, highs, 20)
    ind.avg_volume_20 = sma(volumes, 20)
    ind.high_52w = max(highs)
    ind.low_52w = min(lows)

    if ind.sma_50 is None:
        ind.notes.append("sma_50 unavailable: fewer than 50 bars")
    return ind


# ---------------------------------------------------------------------------
# Trade levels
# ---------------------------------------------------------------------------

@dataclass
class TradeLevels:
    """Entry / target / stop derived from real prices by a stated method."""

    direction: str
    reference_price: float
    entry: float
    target: float
    stop: float
    risk_reward: float
    risk_pct: float
    reward_pct: float
    strategy: str
    basis: Dict[str, Optional[float]] = field(default_factory=dict)
    valid: bool = True
    invalid_reason: str = ""

    def as_dict(self) -> Dict:
        return {
            "direction": self.direction,
            "reference_price": self.reference_price,
            "entry": self.entry,
            "target": self.target,
            "stop": self.stop,
            "risk_reward": self.risk_reward,
            "risk_pct": self.risk_pct,
            "reward_pct": self.reward_pct,
            "strategy": self.strategy,
            "basis": self.basis,
            "valid": self.valid,
            "invalid_reason": self.invalid_reason,
        }


def _round2(value: float) -> float:
    return round(value, 2)


def derive_levels(
    ind: Indicators,
    direction: str = "LONG",
    *,
    atr_stop_multiple: float = 2.0,
    min_risk_reward: float = 1.8,
    min_reward_pct: float = 4.0,
    max_risk_pct: float = 12.0,
    atr_floor_pct: float = 0.015,
) -> TradeLevels:
    """Build a trade plan from real indicator values.

    Method, stated explicitly so it can be shown to the user:

    * **entry** - the last real close. Not a prediction.
    * **stop** - ``2 x ATR(14)`` away from entry, but never tighter than
      ``max(2 x ATR, 1.5% of entry)``. ATR is the stock's own realised
      volatility, so the stop widens for volatile names and tightens for
      quiet ones.
    * **target** - ``entry + reward``, where ``reward`` is the larger of
      ``2 x risk`` and the distance to the 20-bar swing resistance (capped so
      it stays a plausible near-term move).
    * **risk/reward** - recomputed from the rounded levels, never taken from
      any model.

    Returns ``valid=False`` when the inputs cannot support a sane plan, in
    which case the caller must drop the signal.
    """
    direction = (direction or "LONG").upper()
    price = ind.last_close

    def fail(reason: str) -> TradeLevels:
        return TradeLevels(
            direction=direction, reference_price=price, entry=0.0, target=0.0,
            stop=0.0, risk_reward=0.0, risk_pct=0.0, reward_pct=0.0,
            strategy="atr_swing_v1", valid=False, invalid_reason=reason,
        )

    if not price or price <= 0:
        return fail("no real price available")
    if ind.bars < 21:
        return fail(f"insufficient history ({ind.bars} bars, need 21)")
    if ind.atr_14 is None:
        return fail("ATR unavailable")

    # ---- stop ------------------------------------------------------------
    atr_value = ind.atr_14
    risk = max(atr_stop_multiple * atr_value, atr_floor_pct * price)
    risk = min(risk, max_risk_pct / 100.0 * price)

    if direction == "LONG":
        stop = price - risk
        # Prefer a stop below the recent swing low, but only when that stays
        # inside the risk cap - a deep swing low would otherwise silently
        # produce a 13% risk on a name whose ATR implies 4%.
        if ind.support_20 and stop > ind.support_20:
            swing_stop = ind.support_20 * 0.995
            if (price - swing_stop) <= max_risk_pct / 100.0 * price:
                stop = swing_stop
        if stop <= 0:
            return fail("computed stop is non-positive")
        risk = price - stop
    else:
        stop = price + risk
        if ind.resistance_20 and stop < ind.resistance_20:
            swing_stop = ind.resistance_20 * 1.005
            if (swing_stop - price) <= max_risk_pct / 100.0 * price:
                stop = swing_stop
        risk = stop - price

    if risk <= 0:
        return fail("zero risk after stop adjustment")

    # ---- target ----------------------------------------------------------
    reward = max(2.0 * risk, min_reward_pct / 100.0 * price)
    if direction == "LONG":
        swing = ind.resistance_20
        if swing and swing > price:
            reward = max(reward, min(swing - price, 3.0 * risk))
        target = price + reward
    else:
        swing = ind.support_20
        if swing and swing < price:
            reward = max(reward, min(price - swing, 3.0 * risk))
        target = max(price - reward, 0.01)

    entry = _round2(price)
    target = _round2(target)
    stop = _round2(stop)

    if entry <= 0 or target <= 0 or stop <= 0:
        return fail("non-positive level after rounding")

    if direction == "LONG":
        if target <= entry or stop >= entry:
            return fail("inconsistent LONG levels")
    else:
        if target >= entry or stop <= entry:
            return fail("inconsistent SHORT levels")

    risk_value = (entry - stop) if direction == "LONG" else (stop - entry)
    reward_value = (target - entry) if direction == "LONG" else (entry - target)
    rr = reward_value / risk_value if risk_value > 0 else 0.0

    return TradeLevels(
        direction=direction,
        reference_price=entry,
        entry=entry,
        target=target,
        stop=stop,
        risk_reward=round(rr, 2),
        risk_pct=round(risk_value / entry * 100, 2),
        reward_pct=round(reward_value / entry * 100, 2),
        strategy="atr_swing_v1",
        basis={
            "atr_14": ind.atr_14,
            "sma_20": ind.sma_20,
            "sma_50": ind.sma_50,
            "rsi_14": ind.rsi_14,
            "support_20": ind.support_20,
            "resistance_20": ind.resistance_20,
            "reference_close": entry,
            "atr_stop_multiple": atr_stop_multiple,
        },
    )


def trend_bias(ind: Indicators) -> str:
    """Classify trend from computed values only.

    Returns ``bullish`` / ``bearish`` / ``neutral`` / ``unknown``. Derived
    strictly from the SMA and RSI figures in ``ind``; no model involved.

    A dead-flat series must read ``neutral``, not ``bearish``: with no
    movement every "is price above the average" test is False, which would
    otherwise make a flat market look like persistent weakness.
    """
    if ind.sma_20 is None or ind.sma_50 is None or not ind.last_close:
        return "unknown"

    # 0.1% band: below it the market is treated as flat rather than trending.
    band = ind.last_close * 0.001
    above20 = ind.last_close > ind.sma_20 + band
    below20 = ind.last_close < ind.sma_20 - band
    above50 = ind.sma_20 > ind.sma_50 + band
    below50 = ind.sma_20 < ind.sma_50 - band

    if above20 and above50:
        base = "bullish"
    elif below20 and below50:
        base = "bearish"
    else:
        base = "neutral"

    if ind.rsi_14 is not None:
        if ind.rsi_14 >= 70:
            return "bullish_overbought" if base == "bullish" else "overbought"
        if ind.rsi_14 <= 30:
            return "bearish_oversold" if base == "bearish" else "oversold"
    return base


def describe_technicals(ind: Indicators) -> List[str]:
    """Human-readable technical facts, each traceable to a computed number."""
    lines: List[str] = []
    if ind.sma_20 is not None:
        rel = "above" if ind.last_close > ind.sma_20 else "below"
        lines.append(f"Price {rel} 20-DMA (SMA20 {ind.sma_20:.1f})")
    if ind.sma_50 is not None:
        rel = "above" if ind.sma_20 > ind.sma_50 else "below"
        lines.append(f"20-DMA {rel} 50-DMA (SMA50 {ind.sma_50:.1f})")
    else:
        lines.append("50-DMA unavailable (insufficient history)")
    if ind.rsi_14 is not None:
        band = "overbought" if ind.rsi_14 >= 70 else "oversold" if ind.rsi_14 <= 30 else "neutral"
        lines.append(f"RSI(14) {ind.rsi_14:.1f} ({band})")
    else:
        lines.append("RSI(14) unavailable (insufficient history)")
    if ind.atr_14 is not None and ind.last_close:
        lines.append(f"ATR(14) {ind.atr_14:.2f} ({ind.atr_14 / ind.last_close * 100:.2f}% of price)")
    if ind.support_20 is not None:
        lines.append(f"20-bar support {ind.support_20:.2f}")
    if ind.resistance_20 is not None:
        lines.append(f"20-bar resistance {ind.resistance_20:.2f}")
    return lines


def volatility_score(ind: Indicators) -> Optional[float]:
    """ATR as a fraction of price, 0..1-ish. ``None`` when not computable."""
    if not ind.atr_14 or not ind.last_close:
        return None
    return round(ind.atr_14 / ind.last_close, 5)
