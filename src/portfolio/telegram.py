"""
Telegram Notifier
Sends formatted trade alerts
Issue 3: When personal_use_only is true, enforce single-recipient delivery.
"""
import os
import json
import logging
import asyncio
import ssl
from typing import Optional, Dict

import aiohttp

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
if CHAT_ID:
    CHAT_ID = int(CHAT_ID)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ""

# Issue 3: personal-use enforcement
_PERSONAL_USE_MODE = None


def _is_personal_use() -> bool:
    """Return True if personal_use_only is enabled in settings (cached)."""
    global _PERSONAL_USE_MODE
    if _PERSONAL_USE_MODE is None:
        try:
            from src.config import load_settings
            _PERSONAL_USE_MODE = load_settings().get("portfolio", {}).get("personal_use_only", True)
        except Exception:
            _PERSONAL_USE_MODE = True  # default to safe mode
    return _PERSONAL_USE_MODE


def _validate_recipient(chat_id: int) -> bool:
    """Issue 3: In personal_use_only mode, only allow the configured CHAT_ID."""
    if _is_personal_use() and chat_id != CHAT_ID:
        logger.warning(
            f"BLOCKED: personal_use_only=True — refusing to send to chat_id={chat_id} "
            f"(expected {CHAT_ID})"
        )
        return False
    return True


async def send_message(text: str, parse_mode: str = "HTML", chat_id: int = None) -> bool:
    """Send message to Telegram. Issue 3: enforces single-recipient in personal_use_only mode."""
    target_chat = chat_id or CHAT_ID
    if not BOT_TOKEN or not target_chat:
        logger.warning("Telegram not configured — BOT_TOKEN or CHAT_ID missing")
        return False

    # Issue 3: validate recipient
    if not _validate_recipient(target_chat):
        return False

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BASE_URL}/sendMessage",
                json={"chat_id": target_chat, "text": text, "parse_mode": parse_mode},
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=SSL_CTX
            ) as resp:
                if resp.status == 200:
                    logger.info("Telegram message sent successfully")
                    return True
                else:
                    body = await resp.text()
                    logger.error(f"Telegram error {resp.status}: {body[:200]}")
                    return False
    except asyncio.TimeoutError:
        logger.error("Telegram send timed out (15s)")
        return False
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def format_signal(signal: Dict) -> str:
    """Format signal for Telegram"""
    trade = signal.get("trade", {})
    catalyst = signal.get("catalyst", {})
    article = signal.get("article", {})

    direction = trade.get("direction", "LONG")
    emoji = "🟢" if direction == "LONG" else "🔴"
    trade_type = trade.get("trade_type", "BUY")

    lines = [
        f"<b>{emoji} ALPHASCOUT SIGNAL</b>",
        f"",
        f"<b>{trade.get('name', '')} ({trade.get('ticker', '').replace('.NS', '')})</b>",
        f"Type: {trade_type} | {direction}",
        f"Confidence: {trade.get('confidence', 0)}% | R:R {trade.get('risk_reward_ratio', 0):.1f}x",
        f"",
        f"📰 <b>Catalyst</b>: {catalyst.get('type', '')} ({catalyst.get('time_sensitivity', '')})",
        f"💰 {catalyst.get('money_involved', 'N/A')} | {catalyst.get('product_category', '')}",
        f"",
        f"📈 <b>Trade Plan</b>:",
        f"   Entry: {trade.get('entry_strategy', '')}",
        f"   Target: {trade.get('target_price', '')} (+{trade.get('target_pct', 0)}%)",
        f"   Stop: {trade.get('stop_loss_price', '')} (-{trade.get('stop_loss_pct', 0)}%)",
        f"   Hold: {trade.get('hold_days', 0)}-{trade.get('max_hold_days', 0)} days",
        f"",
        f"💡 <b>Thesis</b>: {trade.get('thesis_one_line', '')}",
        f"⚠️ <b>Kill Switch</b>: {trade.get('kill_switch', '')}",
        f"",
        f"🔗 <a href='{article.get('url', '')}'>Read Article</a> | {article.get('source', '')}",
    ]

    if signal.get("ensemble_agreement"):
        lines.append("🤖 <i>Ensemble Agreement: YES</i>")

    return "\n".join(lines)


def format_portfolio_update(positions: Dict) -> str:
    """Format portfolio summary"""
    if not positions:
        return "📭 Portfolio is empty"

    lines = ["<b>📊 PORTFOLIO UPDATE</b>", ""]

    total_pnl = 0
    for p in positions.values():
        pnl_emoji = "🟢" if p.unrealized_pnl >= 0 else "🔴"
        lines.append(
            f"{pnl_emoji} {p.name} ({p.ticker.replace('.NS', '')}) "
            f"| {p.unrealized_pnl_pct:+.1f}% (₹{p.unrealized_pnl:,.0f}) "
            f"| Day {p.days_held()}/{p.max_hold_days}"
        )
        total_pnl += p.unrealized_pnl

    lines.append("")
    total_emoji = "🟢" if total_pnl >= 0 else "🔴"
    lines.append(f"{total_emoji} Total P&L: ₹{total_pnl:,.0f}")

    return "\n".join(lines)


async def send_signal(signal: Dict) -> bool:
    """Send trade signal"""
    return await send_message(format_signal(signal))


async def send_portfolio(positions: Dict) -> bool:
    """Send portfolio update"""
    return await send_message(format_portfolio_update(positions))


async def send_alert(message: str) -> bool:
    """Send custom alert"""
    return await send_message(f"🚨 <b>ALERT</b>\n\n{message}")


# Test
if __name__ == "__main__":
    import asyncio

    async def test():
        if BOT_TOKEN and CHAT_ID:
            await send_message("🤖 AlphaScout bot online!")
            print("Test message sent")
        else:
            print("Telegram not configured")

    asyncio.run(test())