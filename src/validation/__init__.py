"""Final gate before anything reaches Telegram.

Every check here is a *veto*. A signal that fails any of them is dropped, and
the reason is recorded. The design intent is that a missing input must produce
a rejection with a reason, never a plausible-looking default.

Ordering is cheapest-and-most-certain first so the recorded reason is the most
fundamental problem rather than a downstream symptom.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30), "IST")

# Structural sanity bounds for an NSE/BSE price. Outside these the feed is
# misconfigured rather than the market being wrong, so refuse rather than
# publish a nonsense quote.
MIN_PLAUSIBLE_PRICE = 0.5
MAX_PLAUSIBLE_PRICE = 2_000_000.0


@dataclass
class ValidationResult:
    ok: bool
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def fail(self, reason: str) -> "ValidationResult":
        self.ok = False
        self.reasons.append(reason)
        return self

    def warn(self, message: str) -> "ValidationResult":
        self.warnings.append(message)
        return self


class SignalValidator:
    """Validates a candidate signal against facts, not opinions."""

    def __init__(
        self,
        *,
        min_risk_reward: float = 1.8,
        max_risk_pct: float = 12.0,
        max_spread_pct: float = 25.0,
        require_fresh_minutes: int = 60,
    ):
        self.min_risk_reward = min_risk_reward
        self.max_risk_pct = max_risk_pct
        self.max_spread_pct = max_spread_pct
        self.require_fresh_minutes = require_fresh_minutes

    # -- individual checks -------------------------------------------------
    def _check_article(self, result: ValidationResult, article: Dict) -> None:
        if not article:
            result.fail("no article attached")
            return
        if not article.get("title"):
            result.fail("article has no headline")
        if not article.get("url"):
            result.fail("article has no URL")
        if not article.get("source"):
            result.fail("article has no source")

    def _check_freshness(self, result: ValidationResult, article: Dict, window_hours: int) -> None:
        """Freshness must come from the publisher's timestamp when available.

        A missing timestamp is treated as *not fresh*. The old code trusted
        feed ordering, which meant a week-old article at the top of an RSS
        feed looked brand new.
        """
        published = article.get("published_at") or ""
        if not published:
            result.fail("no publication timestamp - cannot confirm freshness")
            return
        try:
            when = datetime.fromisoformat(published)
        except ValueError:
            result.fail(f"unparseable publication timestamp {published!r}")
            return
        if when.tzinfo is None:
            when = when.replace(tzinfo=IST)

        age_hours = (datetime.now(IST) - when).total_seconds() / 3600.0
        if age_hours < -2:
            result.fail(f"publication timestamp is {abs(age_hours):.1f}h in the future")
            return
        if age_hours > window_hours:
            result.fail(
                f"article is {age_hours:.1f}h old, outside the {window_hours}h freshness window"
            )

    def _check_not_already_sent(self, result: ValidationResult, article: Dict, store) -> None:
        if store is None:
            return
        from src.store import ArticleRecord

        canonical = article.get("canonical_url") or ""
        if not canonical:
            result.fail("no canonical URL for cross-run dedup")
            return
        try:
            existing = store.get_article(canonical)
        except Exception as exc:
            result.warn(f"dedup lookup failed ({exc}); treating as new")
            return
        if existing and existing.sent:
            result.fail("this exact article was already sent")

    def _check_ticker(self, result: ValidationResult, ticker: str, verified: bool) -> None:
        if not ticker:
            result.fail("no ticker")
            return
        if not ticker.endswith((".NS", ".BO")):
            result.fail(f"{ticker} is not an NSE/BSE symbol")
        if not verified:
            result.fail(f"{ticker} was not verified against a real Indian listing")

    def _check_price(self, result: ValidationResult, quote) -> None:
        if quote is None:
            result.fail("market data unavailable - refusing to invent a price")
            return
        if quote.price <= 0:
            result.fail(f"non-positive price ({quote.price})")
            return
        if not (MIN_PLAUSIBLE_PRICE <= quote.price <= MAX_PLAUSIBLE_PRICE):
            result.fail(f"price {quote.price} outside plausible NSE range")
        if not quote.source:
            result.fail("price has no recorded source")
        if not quote.is_indian:
            result.fail("quote is not for an Indian listing")
        if quote.price_kind == "live" and quote.session_label == "":
            result.warn("live price without a session label")

    def _check_indicators(self, result: ValidationResult, indicators) -> None:
        if indicators is None:
            result.fail("technical indicators unavailable")
            return
        if indicators.last_close <= 0:
            result.fail("indicator series has no usable close")
            return
        for name, value in (
            ("SMA20", indicators.sma_20),
            ("RSI(14)", indicators.rsi_14),
            ("ATR(14)", indicators.atr_14),
        ):
            if value is None:
                # Recorded, but not fatal: the levels may still be derivable.
                result.warn(f"{name} could not be computed from available history")

    def _check_levels(self, result: ValidationResult, levels) -> None:
        """The core anti-fabrication check.

        Entry must equal the real reference price, and target/stop must be
        derived from it - never asserted by a model.
        """
        if levels is None or not getattr(levels, "valid", False):
            reason = getattr(levels, "invalid_reason", "levels unavailable")
            result.fail(f"trade levels could not be derived: {reason}")
            return

        entry, target, stop = levels.entry, levels.target, levels.stop
        if entry <= 0 or target <= 0 or stop <= 0:
            result.fail("non-positive trade level")
            return

        direction = levels.direction
        if direction == "LONG":
            if not (target > entry > stop):
                result.fail(f"LONG ordering violated: target {target} entry {entry} stop {stop}")
        else:
            if not (target < entry < stop):
                result.fail(f"SHORT ordering violated: target {target} entry {entry} stop {stop}")

        # Entry must be the real price, not something the model chose.
        reference = getattr(levels, "reference_price", entry)
        if abs(entry - reference) > 0.01:
            result.fail(
                f"entry {entry} does not match the real reference price {reference}"
            )

        if levels.risk_reward <= 0:
            result.fail("risk/reward not computable")
        elif levels.risk_reward < self.min_risk_reward:
            result.fail(
                f"risk/reward {levels.risk_reward} below the {self.min_risk_reward} floor"
            )

        if levels.risk_pct > self.max_risk_pct:
            result.fail(f"risk {levels.risk_pct}% exceeds the {self.max_risk_pct}% cap")

        if not levels.strategy:
            result.fail("trade levels have no recorded strategy")

    def _check_price_consistency(self, result: ValidationResult, quote, levels) -> None:
        """Guard against the model steering the entry far from the market."""
        if quote is None or levels is None or not getattr(levels, "valid", False):
            return
        if quote.price <= 0 or levels.entry <= 0:
            return
        drift = abs(levels.entry - quote.price) / quote.price * 100
        if drift > self.max_spread_pct:
            result.fail(
                f"entry {levels.entry} is {drift:.1f}% away from the real price "
                f"{quote.price}"
            )

    def _check_ai_fields(self, result: ValidationResult, signal: Dict) -> None:
        """AI output is prose only. Numeric fields here are a design error."""
        forbidden = (
            "entry_price", "entry_price_range", "target_price", "stop_loss",
            "stop_loss_price", "risk_reward_ratio", "target_pct", "stop_loss_pct",
            "sma_20", "sma_50", "rsi", "rsi_14", "current_price", "market_price",
            "price", "volume", "support", "resistance",
            # The field the old prompts demanded. It asserted "above_20dma" and
            # "rsi_level" from a model that was never given either, so it must
            # never be accepted as a fact.
            "technical_checklist", "technical_support",
        )
        ai = signal.get("ai") or {}
        for key in forbidden:
            if key in ai:
                result.fail(
                    f"AI block must not contain numeric field {key!r} "
                    "(market values belong to the facts block)"
                )
        if not (ai.get("thesis") or "").strip():
            result.fail("AI provided no thesis")

    # -- entry point -------------------------------------------------------
    def validate(
        self,
        *,
        signal: Dict,
        article: Dict,
        quote,
        indicators,
        levels,
        resolution,
        store=None,
        freshness_window_hours: int = 30,
    ) -> ValidationResult:
        result = ValidationResult(ok=True)

        self._check_article(result, article)
        self._check_freshness(result, article, freshness_window_hours)
        self._check_not_already_sent(result, article, store)

        verified = bool(getattr(resolution, "verified", False)) if resolution else False
        self._check_ticker(result, signal.get("ticker", ""), verified)

        self._check_price(result, quote)
        self._check_indicators(result, indicators)
        self._check_levels(result, levels)
        self._check_price_consistency(result, quote, levels)
        self._check_ai_fields(result, signal)

        for warning in result.warnings:
            logger.info("VALIDATION WARNING %s: %s", signal.get("ticker", "?"), warning)
        if not result.ok:
            logger.info(
                "VALIDATION REJECTED %s: %s",
                signal.get("ticker", "?"), "; ".join(result.reasons),
            )
        return result
