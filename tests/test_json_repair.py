"""Offline tests for LLM JSON parsing + truncation repair in providers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.providers import BaseProvider


class _P(BaseProvider):
    """Concrete provider exposing _parse_json without network init."""

    def __init__(self):
        # skip BaseProvider.__init__ (sets up keys/stats) — only need parsers
        self.name = "test"

    def generate(self, prompt, system, max_tokens=2000, temperature=0.2):
        return None


p = _P()


class TestParseJson:
    def test_direct(self):
        assert p._parse_json('{"a": 1}') == {"a": 1}

    def test_markdown_fence(self):
        assert p._parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_think_tags_stripped(self):
        assert p._parse_json('<think>hmm</think>{"a": 1}') == {"a": 1}

    def test_prose_around_json(self):
        assert p._parse_json('Here you go:\n{"a": 1}\nDone.') == {"a": 1}


class TestTruncationRepair:
    def test_truncated_string_value_in_nested_object(self):
        # Real failure mode from logs: entity extraction cut mid-"reason"
        raw = '{\n  "companies": [\n    {\n      "name": "Paras Defence Limited",\n' \
              '      "ticker": "PARASDEF.NS",\n      "market_cap_category": "SMALL",\n' \
              '      "role": "SUPPLIER",\n      "reason": "Paras Defence supplies p'
        out = p._parse_json(raw)
        assert out is not None
        comps = out.get("companies", [])
        assert len(comps) == 1
        assert comps[0]["name"] == "Paras Defence Limited"
        assert comps[0]["ticker"] == "PARASDEF.NS"
        assert comps[0]["role"] == "SUPPLIER"

    def test_truncated_after_complete_element(self):
        raw = '{"predictions": [{"ticker": "A.NS", "direction": "UP"}, {"ticker": "B.NS", "dir'
        out = p._parse_json(raw)
        assert out is not None
        tickers = [x["ticker"] for x in out["predictions"]]
        assert "A.NS" in tickers  # complete element always salvaged
        # partial second object must never contain the truncated key
        for x in out["predictions"]:
            assert "dir" not in x

    def test_truncated_value_at_eof_closes_cleanly(self):
        raw = '{"code": "function() { return 1 }", "x": 1'
        out = p._parse_json(raw)
        assert out is not None
        assert out.get("x") == 1

    def test_truncated_mid_number(self):
        raw = '{"confidence": 7'
        out = p._parse_json(raw)
        assert out is None or isinstance(out, dict)

    def test_no_json_at_all(self):
        assert p._parse_json("The user wants structured output about defence.") is None

    def test_escaped_quotes_in_truncated_string(self):
        raw = '{"note": "said \\"hello\\" and then more trun'
        out = p._parse_json(raw)
        # may salvage empty-ish or fail; must not raise
        assert out is None or isinstance(out, dict)
