"""Offline tests for pipeline dataclass handling and triage field propagation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.pipeline import ImpactPrediction


def test_from_dict_strips_unknown_keys():
    d = {
        "ticker": "X.NS",
        "name": "X Ltd",
        "direction": "UP",
        "expected_move_pct": 10,
        "confidence": 70,
        "reasoning": "r",
        "event_summary": "should be stripped",  # not a dataclass field
        "totally_unknown": 1,
    }
    pred = ImpactPrediction.from_dict(d)
    assert pred.ticker == "X.NS"
    assert not hasattr(pred, "event_summary")


def test_from_dict_fixes_llm_typo():
    d = {
        "ticker": "X.NS", "name": "X", "direction": "UP",
        "expected_move_pct": 10, "confidence": 70, "reasoning": "order win",
        "catalyst_to_relevity": "Mumbai HQ",  # LLM typo for catalyst_to_revenue
    }
    pred = ImpactPrediction.from_dict(d)
    assert pred.catalyst_to_revenue == "Mumbai HQ"
