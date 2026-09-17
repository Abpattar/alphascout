"""Offline tests for Groq rate-limit retry parsing and ticker alias fixes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.providers import GroqMultiKeyProvider


class TestExtractRetryAfter:
    def test_seconds(self):
        msg = "Rate limit reached... Please try again in 2.055s. Need more tokens?"
        assert GroqMultiKeyProvider._extract_retry_after(msg) == 2.055

    def test_milliseconds(self):
        msg = "Please try again in 360ms."
        assert abs(GroqMultiKeyProvider._extract_retry_after(msg) - 0.36) < 1e-9

    def test_long_seconds(self):
        msg = "Please try again in 12.9375s"
        assert GroqMultiKeyProvider._extract_retry_after(msg) == 12.9375

    def test_no_match(self):
        assert GroqMultiKeyProvider._extract_retry_after("some other error") is None


def test_paras_alias_resolves_to_real_ticker():
    # Yahoo/NSE ground truth: Paras Defence trades as PARAS.NS (PARASDEF.NS is dead)
    from src.universe.ticker_map import TICKER_ALIASES
    from src.universe.builder import _KNOWN_TICKER_MAP

    assert TICKER_ALIASES["paras defence"] == "PARAS.NS"
    assert _KNOWN_TICKER_MAP["PARASDEF"] == "PARAS.NS"
    assert _KNOWN_TICKER_MAP["PARASDEF.NS"] == "PARAS.NS"


def test_solar_industries_alias():
    from src.universe.ticker_map import TICKER_ALIASES
    assert TICKER_ALIASES["solar industries"] == "SOLARINDS.NS"
