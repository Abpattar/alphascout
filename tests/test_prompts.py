"""Offline tests for prompt builders — especially event_summary propagation (trade setup)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.prompts import (
    build_trade_prompt,
    build_triage_prompt,
    build_quick_filter_prompt,
)


def test_trade_prompt_includes_event_summary():
    pred = {
        "name": "Webel Solar",
        "ticker": "WEBELSOLAR.NS",
        "direction": "UP",
        "expected_move_pct": 12,
        "confidence": 72,
        "reasoning": "Large order win boosts revenue",
        "event_summary": "Company won a 500 crore solar order",
        "catalyst_type": "ORDER_WIN",
    }
    _system, prompt = build_trade_prompt(pred, current_price=123.4)
    assert "500 crore solar order" in prompt
    assert "ORDER_WIN" in prompt
    assert "123.4" in prompt


def test_trade_prompt_empty_event_summary_does_not_crash():
    pred = {"name": "X", "ticker": "X.NS", "direction": "UP"}
    _system, prompt = build_trade_prompt(pred, current_price=0)
    assert "CATALYST:" in prompt


def test_triage_prompt_truncates_content():
    article = {"title": "T", "content": "C" * 5000, "source": "S"}
    _system, prompt = build_triage_prompt(article)
    # content truncated to 2500 chars
    assert prompt.count("CCCC") > 0


def test_quick_filter_prompt_fields():
    _system, prompt = build_quick_filter_prompt("Some title", "Some snippet")
    assert "Some title" in prompt and "Some snippet" in prompt
