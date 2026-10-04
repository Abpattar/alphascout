"""Single entry point for LLM calls in the new pipeline.

Reuses the existing provider registry in :mod:`src.ai.providers` so the
multi-key Groq rotation, per-provider fallback and rate-limit handling stay in
one place. What is new here is the contract:

* return parsed JSON, or ``None`` - never a string, never a guess
* one bounded retry that asks the model to fix its own output
* numeric keys stripped defensively, so a model that ignores the prompt and
  emits a price cannot put it into the signal

The task name passed to the registry (``interpret``) is intentionally not in
its routing table, so it uses the registry's default fallback chain.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Keys that must never survive from a model response into a signal. The
# validation layer rejects a signal containing them; stripping here means a
# stray number cannot even reach the record.
FORBIDDEN_NUMERIC_KEYS = frozenset({
    "entry_price", "entry_price_range", "target_price", "stop_loss",
    "stop_loss_price", "risk_reward_ratio", "target_pct", "stop_loss_pct",
    "current_price", "market_price", "price", "sma_20", "sma_50", "rsi",
    "rsi_14", "atr", "atr_14", "volume", "support", "resistance",
    "technical_checklist", "hold_days", "position_size_pct",
})

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def extract_json(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Best-effort JSON recovery from a model response."""
    if not text:
        return None
    cleaned = _THINK.sub("", text).strip()

    if "```" in cleaned:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1)

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    block = _JSON_BLOCK.search(cleaned)
    if not block:
        return None
    try:
        parsed = json.loads(block.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def strip_forbidden(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drop any numeric market key a model may have emitted despite the prompt."""
    if not isinstance(payload, dict):
        return {}
    return {
        key: value for key, value in payload.items()
        if key.lower() not in FORBIDDEN_NUMERIC_KEYS
    }


class AIClient:
    """JSON-returning wrapper over the provider registry."""

    def __init__(self, task: str = "interpret"):
        self.task = task
        self._registry = None
        self.calls = 0
        self.failures = 0
        self.last_error = ""

    def _get_registry(self):
        if self._registry is None:
            from src.ai.providers import get_registry

            self._registry = get_registry()
        return self._registry

    def available(self) -> bool:
        try:
            from src.config import validate_api_keys

            return bool(validate_api_keys().get("groq"))
        except Exception as exc:
            logger.warning("AI availability check failed: %s", exc)
            return False

    def ask_json(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 1200,
        temperature: float = 0.1,
        max_attempts: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Call the model and return a dict, or ``None``.

        Retries once with an explicit "return valid JSON only" instruction
        before giving up. Never raises: an AI outage must degrade to "no
        signal", not to a broken run.
        """
        registry = self._get_registry()
        current_prompt = prompt
        last_error = ""
        self.last_error = ""

        for attempt in range(1, max_attempts + 1):
            self.calls += 1
            try:
                raw = registry.execute_task(
                    self.task,
                    system,
                    current_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    # One agreeing provider is enough. The registry defaults to
                    # min_agree=2, which calls up to four providers for every
                    # single assessment - four times the rate-limit spend for a
                    # result that is then discarded anyway. Providers still
                    # fail over on error, which is the behaviour we want.
                    min_agree=1,
                )
            except Exception as exc:
                logger.warning("AI call failed (attempt %d): %s", attempt, exc)
                last_error = str(exc)
                continue

            if not raw:
                last_error = "empty response"
                self.last_error = last_error
                logger.info("AI returned nothing (attempt %d)", attempt)
            else:
                parsed = extract_json(raw if isinstance(raw, str) else json.dumps(raw))
                if parsed is not None:
                    cleaned = strip_forbidden(parsed)
                    dropped = set(parsed) - set(cleaned)
                    if dropped:
                        logger.info("Dropped forbidden numeric keys from AI output: %s", dropped)
                    return cleaned
                last_error = "response was not valid JSON"
                self.last_error = last_error

            if attempt < max_attempts:
                current_prompt = (
                    prompt
                    + "\n\nYour previous reply could not be parsed. Reply with ONE JSON "
                    "object and nothing else - no prose, no markdown fence."
                )

        self.failures += 1
        self.last_error = last_error
        logger.warning("AI gave up after %d attempts (%s)", max_attempts, last_error)
        return None

    def ask_text(self, system: str, prompt: str, *, max_tokens: int = 400) -> str:
        """Free-text call used only for optional narrative enrichment."""
        try:
            registry = self._get_registry()
            self.calls += 1
            raw = registry.execute_task(
                self.task, system, prompt,
                max_tokens=max_tokens, temperature=0.3,
            )
            return raw if isinstance(raw, str) else ""
        except Exception as exc:
            logger.warning("AI text call failed: %s", exc)
            return ""


_shared: Optional[AIClient] = None


def get_client() -> AIClient:
    global _shared
    if _shared is None:
        _shared = AIClient()
    return _shared


def reset_client() -> None:
    global _shared
    _shared = None
