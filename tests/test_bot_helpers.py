"""Offline tests for bot input parsing helpers and date math."""
from datetime import date, timedelta

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.portfolio.bot import _parse_int, _parse_number, _safe_int, _due_date, _patience_date


class TestParseNumber:
    def test_plain(self):
        assert _parse_number("830") == 830.0

    def test_decimal(self):
        assert _parse_number("830.5") == 830.5

    def test_rupee_and_commas(self):
        assert _parse_number("₹1,250.75") == 1250.75

    def test_embedded_in_sentence(self):
        assert _parse_number("I bought at 812 per share") == 812.0

    def test_no_number(self):
        assert _parse_number("nope") is None
        assert _parse_number("") is None


class TestParseInt:
    def test_plain(self):
        assert _parse_int("25") == 25

    def test_skip_defaults_to_one(self):
        assert _parse_int("skip") == 1
        assert _parse_int("default") == 1

    def test_no_number_returns_none(self):
        assert _parse_int("abc") is None


class TestSafeInt:
    def test_valid(self):
        assert _safe_int("42") == 42

    def test_invalid(self):
        assert _safe_int("x") is None
        assert _safe_int(None) is None


class TestDateMath:
    def test_due_date_first_reminder(self):
        cfg = {"reminder_days": [7, 30]}
        expected = (date.today() + timedelta(days=7)).isoformat()
        assert _due_date(cfg, 0) == expected

    def test_due_date_out_of_range_clamps(self):
        cfg = {"reminder_days": [7]}
        expected = (date.today() + timedelta(days=7)).isoformat()
        assert _due_date(cfg, 5) == expected

    def test_patience_date(self):
        cfg = {"patience_days": 30}
        expected = (date.today() + timedelta(days=30)).isoformat()
        assert _patience_date(cfg) == expected
