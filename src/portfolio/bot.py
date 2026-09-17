"""
AlphaScout Telegram Interactive Bot
====================================
Long-polling loop that listens for signal-confirmation buttons
("I Bought It" / "Skip"), records manual holdings, and sends
7-day / 30-day sell reminders.

Manual-only flow: the user buys/sells in their broker; this bot only
tracks + reminds. No auto-execution.

Requires `python main.py scheduler` running (reminders + button
listening work while this process is alive).
"""
import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Dict, Optional

import aiohttp

from src.config import get_holdings_config
from src.portfolio.telegram import (
    BASE_URL,
    BOT_TOKEN,
    SSL_CTX,
    answer_callback_query,
    edit_message_reply_markup,
    make_inline_keyboard,
    send_message,
)

logger = logging.getLogger(__name__)

POLL_TIMEOUT = 25
POLL_INTERVAL = 1.5

_pending: Dict[int, dict] = {}


# ─────────────────────────────────────────────────────────────────────
# PRICE HELPERS
# ─────────────────────────────────────────────────────────────────────

def fetch_current_price(ticker: str) -> Optional[float]:
    """Best-effort live price via yfinance. Returns None if unavailable."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        fast = getattr(t, "fast_info", None)
        try:
            p = float(fast.last_price) if fast is not None else None
        except Exception:
            p = None
        if p:
            return p
        hist = t.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.debug(f"fetch_current_price({ticker}) failed: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────
# POLLING LOOP
# ─────────────────────────────────────────────────────────────────────

async def poll_updates():
    """Run the long-polling getUpdates loop forever. Start as an asyncio task."""
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set — interactive bot disabled (polling parked)")
        while True:
            await asyncio.sleep(3600)
    offset = 0
    logger.info("Telegram bot polling started")
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{BASE_URL}/getUpdates",
                    params={"offset": offset, "timeout": POLL_TIMEOUT},
                    timeout=aiohttp.ClientTimeout(total=POLL_TIMEOUT + 15),
                    ssl=SSL_CTX,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for upd in data.get("result", []):
                            offset = upd["update_id"] + 1
                            await _handle_update(upd)
                    else:
                        logger.warning(f"getUpdates HTTP {resp.status}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Poll error: {e}")
            await asyncio.sleep(3)
        await asyncio.sleep(POLL_INTERVAL)


async def _handle_update(update: dict):
    if "callback_query" in update:
        await _handle_callback(update["callback_query"])
    elif "message" in update:
        await _handle_message(update["message"])


# ─────────────────────────────────────────────────────────────────────
# CALLBACK HANDLERS (button presses)
# ─────────────────────────────────────────────────────────────────────

async def _handle_callback(cb: dict):
    data = cb.get("data", "")
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    cb_id = cb.get("id", "")

    if data.startswith("bought:"):
        signal_id = data[len("bought:"):]
        await _handle_bought(chat_id, message_id, cb_id, signal_id)
    elif data.startswith("skip:"):
        signal_id = data[len("skip:"):]
        await answer_callback_query(cb_id, "Skipped")
        await edit_message_reply_markup(chat_id, message_id)
        await send_message(f"🙅 Skipped {signal_id.split('_')[0]}. No reminder set.")
    elif data.startswith("sold:"):
        holding_id = _safe_int(data[len("sold:"):])
        await _handle_sold(chat_id, message_id, cb_id, holding_id)
    elif data.startswith("extend:"):
        holding_id = _safe_int(data[len("extend:"):])
        await _handle_extend(chat_id, message_id, cb_id, holding_id)
    else:
        await answer_callback_query(cb_id, "Unknown action")


async def _handle_bought(chat_id: int, message_id: int, cb_id: str, signal_id: str):
    from src.storage.db import get_db
    signal = get_db().get_signal(signal_id)
    if not signal:
        await answer_callback_query(cb_id, "Signal not found in DB")
        await send_message(
            "⚠️ Could not find that signal in the database. "
            "It may have been sent before the database existed."
        )
        return

    await answer_callback_query(cb_id, "OK - tell me your buy price")
    await edit_message_reply_markup(chat_id, message_id)

    ticker_short = signal["ticker"].replace(".NS", "").replace(".BO", "")
    _pending[chat_id] = {"step": "entry_price", "signal": dict(signal)}
    await send_message(
        f"Great! 💰 At what price did you buy <b>{signal['name']} ({ticker_short})</b>?\n"
        f"Reply a number, e.g. <b>830</b>"
    )


async def _handle_sold(chat_id: int, message_id: int, cb_id: str, holding_id: Optional[int]):
    from src.storage.db import get_db
    if holding_id is None:
        await answer_callback_query(cb_id, "Invalid holding")
        return
    holding = get_db().get_holding(holding_id)
    if not holding:
        await answer_callback_query(cb_id, "Holding not found")
        return

    await answer_callback_query(cb_id, "OK - tell me your sell price")
    await edit_message_reply_markup(chat_id, message_id)

    ticker_short = holding["ticker"].replace(".NS", "").replace(".BO", "")
    _pending[chat_id] = {"step": "sell_price", "holding": holding}
    await send_message(
        f"💸 At what price did you sell <b>{holding['name']} ({ticker_short})</b>?\n"
        f"Reply a number, e.g. <b>912</b>"
    )


async def _handle_extend(chat_id: int, message_id: int, cb_id: str, holding_id: Optional[int]):
    from src.storage.db import get_db
    if holding_id is None:
        await answer_callback_query(cb_id, "Invalid holding")
        return
    db = get_db()
    holding = db.get_holding(holding_id)
    if not holding:
        await answer_callback_query(cb_id, "Holding not found")
        return

    cfg = get_holdings_config()
    patience = cfg.get("patience_days", 30)
    extend_days = cfg.get("extend_days", 30)

    days_held = (date.today() - date.fromisoformat(holding["buy_date"])).days
    if days_held >= patience:
        new_deadline = (date.today() + timedelta(days=extend_days)).isoformat()
        db.extend_holding(holding_id, new_deadline)
        await answer_callback_query(cb_id, "Extended by " + str(extend_days) + " days")
        await edit_message_reply_markup(chat_id, message_id)
        await send_message(
            f"🙂 Still holding <b>{holding['name']}</b>. Extended to <b>{new_deadline}</b> "
            f"(+{extend_days} days). I'll remind you then."
        )
    else:
        await answer_callback_query(cb_id, "Noted")
        await send_message(
            f"👍 Noted, keeping <b>{holding['name']}</b> on the watch list. "
            f"Next reminder on day {patience}."
        )


# ─────────────────────────────────────────────────────────────────────
# MESSAGE HANDLERS (user replies to bot prompts)
# ─────────────────────────────────────────────────────────────────────

async def _handle_message(msg: dict):
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    if chat_id in _pending:
        await _handle_pending_input(chat_id, text)
        return

    if text.lower() in ("/holds", "/holdings", "holds"):
        await _send_holdings_list(chat_id)


async def _handle_pending_input(chat_id: int, text: str):
    state = _pending.get(chat_id)
    if not state:
        return
    step = state.get("step")

    if step == "entry_price":
        price = _parse_number(text)
        if price is None:
            await send_message("That doesn't look like a number 🤔. Reply like <b>830</b> or <b>830.5</b>")
            return
        state["entry_price"] = price
        state["step"] = "quantity"
        await send_message(
            f"✅ Buy price recorded at <b>₹{price:,.2f}</b>.\n"
            f"How many shares? Reply a number, or type <b>skip</b> for default (1)."
        )

    elif step == "quantity":
        qty = _parse_int(text)
        qty = qty if qty and qty > 0 else 1
        signal = state.get("signal")
        holding = {
            "signal_id": signal["signal_id"],
            "ticker": signal["ticker"],
            "name": signal.get("name", signal["ticker"]),
            "entry_price": state.get("entry_price", 0),
            "quantity": qty,
            "target_price": signal.get("target_price", 0),
            "stop_price": signal.get("stop_loss_price", 0),
            "buy_date": date.today().isoformat(),
            "sell_due_date": _due_date(get_holdings_config(), 0),
            "patience_deadline": _patience_date(get_holdings_config()),
        }
        from src.storage.db import get_db
        holding_id = get_db().store_holding(holding)
        del _pending[chat_id]
        if not holding_id:
            await send_message("⚠️ Failed to store the holding. Check the logs.")
            return
        ticker_short = holding["ticker"].replace(".NS", "").replace(".BO", "")
        await send_message(
            f"📌 <b>{holding['name']} ({ticker_short})</b> stored in hold.\n"
            f"   Buy: ₹{holding['entry_price']:,.2f} x {qty}\n"
            f"   Sell reminder: <b>{holding['sell_due_date']}</b> (day "
            f"{get_holdings_config().get('reminder_days', [7, 30])[0]})\n"
            f"   Patience deadline: <b>{holding['patience_deadline']}</b>"
        )

    elif step == "sell_price":
        price = _parse_number(text)
        if price is None:
            await send_message("That doesn't look like a number 🤔. Reply like <b>912</b>")
            return
        holding = state.get("holding")
        from src.storage.db import get_db
        db = get_db()
        result = db.mark_holding_sold(
            holding["id"], price, date.today().isoformat(), exit_reason="MANUAL_SELL"
        )
        del _pending[chat_id]
        if result is None:
            await send_message("⚠️ Could not record the sale.")
            return
        emoji = "🟢" if result["pnl"] >= 0 else "🔴"
        await send_message(
            f"{emoji} <b>{holding['name']}</b> marked as SOLD at ₹{price:,.2f}.\n"
            f"   P&L: {result['pnl']:+,.0f} ({result['pnl_pct']:+.1f}%)"
        )


async def _send_holdings_list(chat_id: int):
    from src.storage.db import get_db
    holdings = get_db().get_holdings("HOLDING")
    if not holdings:
        await send_message("📭 No holdings right now.")
        return
    lines = ["<b>📌 CURRENT HOLDS</b>", ""]
    for h in holdings:
        ticker_short = h["ticker"].replace(".NS", "").replace(".BO", "")
        lines.append(
            f"• {h['name']} ({ticker_short}) | ₹{h['entry_price']:,.2f} x {h['quantity']} "
            f"| bought {h['buy_date']}"
        )
    await send_message("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────
# REMINDERS
# ─────────────────────────────────────────────────────────────────────

async def run_reminder_check():
    """Send sell reminders for due holdings. Called periodically by the scheduler.
    Sends at most `nudges_per_day` messages per due day (deduped by date)."""
    from src.storage.db import get_db
    db = get_db()
    cfg = get_holdings_config()
    reminder_days = cfg.get("reminder_days", [7, 30])
    nudges_per_day = cfg.get("nudges_per_day", 2)
    patience = cfg.get("patience_days", 30)

    today = date.today()
    today_s = today.isoformat()
    db.reset_holdings_nudges(today_s)

    for h in db.get_holdings("HOLDING"):
        try:
            days_held = (today - date.fromisoformat(h["buy_date"])).days
        except ValueError:
            continue
        if days_held not in reminder_days:
            continue

        if h.get("nudges_today", 0) >= nudges_per_day:
            continue

        price = await asyncio.to_thread(fetch_current_price, h["ticker"])
        text = _build_reminder_text(h, days_held, patience, price)

        reply_markup = make_inline_keyboard([
            [{"text": "✅ I Sold It", "callback_data": f"sold:{h['id']}"}],
            [{"text": "🙂 Still Holding", "callback_data": f"extend:{h['id']}"}],
        ])
        await send_message(text, reply_markup=reply_markup)
        db.mark_holding_reminded(h["id"], today_s, h.get("nudges_today", 0) + 1)


def _build_reminder_text(h: dict, days_held: int, patience: int, price: Optional[float]) -> str:
    ticker_short = h["ticker"].replace(".NS", "").replace(".BO", "")
    pnl_line = ""
    if price:
        pnl_pct = (price - h["entry_price"]) / h["entry_price"] * 100
        emoji = "🟢" if pnl_pct >= 0 else "🔴"
        pnl_line = f"   Current: ₹{price:,.2f} ({emoji} {pnl_pct:+.1f}%)\n"
    extra = ""
    if days_held >= patience:
        extra = "   ⚠️ One month is up — sell or press 'Still Holding' to extend.\n"

    return (
        f"⏰ <b>SELL REMINDER</b> — {h['name']} ({ticker_short})\n"
        f"   Bought: {h['buy_date']} @ ₹{h['entry_price']:,.2f} x {h['quantity']}\n"
        + pnl_line +
        f"   Held: {days_held} days\n"
        + extra +
        f"Time to review and decide — sell, or keep holding."
    )


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _due_date(cfg: dict, index: int) -> str:
    days = cfg.get("reminder_days", [7, 30])
    offset = days[min(index, len(days) - 1)] if days else 7
    return (date.today() + timedelta(days=offset)).isoformat()


def _patience_date(cfg: dict) -> str:
    days = cfg.get("patience_days", 30)
    return (date.today() + timedelta(days=days)).isoformat()


def _parse_number(text: str) -> Optional[float]:
    if not text:
        return None
    nums = re.findall(r"\d[\d,]*\.?\d*", text.replace("₹", "").replace(",", ""))
    if not nums:
        return None
    try:
        return float(nums[0])
    except ValueError:
        return None


def _parse_int(text: str) -> Optional[int]:
    if not text or text.lower() in ("skip", "default", "1"):
        return 1
    nums = re.findall(r"\d+", text)
    if not nums:
        return None
    try:
        return int(nums[0])
    except ValueError:
        return None


def _safe_int(val: str) -> Optional[int]:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
