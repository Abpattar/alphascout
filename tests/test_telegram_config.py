"""Offline tests for telegram config hardening (non-numeric CHAT_ID must not crash)."""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _reload_telegram(monkeypatch, token, chat_id):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    if chat_id is None:
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    else:
        monkeypatch.setenv("TELEGRAM_CHAT_ID", chat_id)
    import src.portfolio.telegram as tg
    return importlib.reload(tg)


def test_valid_chat_id_parses_to_int(monkeypatch):
    tg = _reload_telegram(monkeypatch, "123:abc", "5096981721")
    assert tg.CHAT_ID == 5096981721


def test_non_numeric_chat_id_becomes_none_not_crash(monkeypatch):
    tg = _reload_telegram(monkeypatch, "123:abc", "not-a-number@chat")
    assert tg.CHAT_ID is None
    assert tg.BASE_URL  # token still set


def test_missing_chat_id_is_none(monkeypatch):
    tg = _reload_telegram(monkeypatch, "123:abc", None)
    assert tg.CHAT_ID is None


def test_no_token_disables_base_url(monkeypatch):
    tg = _reload_telegram(monkeypatch, "", "42")
    assert tg.BASE_URL == ""
