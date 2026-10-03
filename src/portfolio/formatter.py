"""Telegram message construction for validated signals.

The formatting goal is that a reader can tell, at a glance, which numbers
came from a market feed and which were computed by this system. Nothing is
presented as an exchange price unless it is one.

Sections are labelled:

* ``MARKET DATA``     - retrieved from the quote provider
* ``CALCULATED``      - computed here from real prices by a stated method
* ``AI ASSESSMENT``   - the model's interpretation, explicitly marked

Untrusted text is HTML-escaped before assembly, because a headline or thesis
containing ``<`` or ``&`` otherwise makes Telegram reject the whole message
with HTTP 400 and the signal is silently lost.
"""
from __future__ import annotations

import html
import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

IST_LABEL = "IST"


def esc(value: Any) -> str:
    """Escape untrusted text for Telegram HTML parse mode.

    Model output and scraped headlines routinely contain ``<``, ``>`` and
    ``&``. Left raw, Telegram refuses the entire message.
    """
    if value is None:
        return ""
    return html.escape(str(value), quote=False)


def esc_attr(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _fmt(value: Optional[float], prefix: str = "₹", decimals: int = 2) -> str:
    if value is None or value == 0:
        return "n/a"
    return f"{prefix}{value:,.{decimals}f}"


def _fmt_num(value: Optional[float], decimals: int = 1, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:,.{decimals}f}{suffix}"


def _price_kind_label(kind: str) -> str:
    return {
        "live": "LIVE",
        "previous_close": "PREVIOUS CLOSE",
        "last_close": "LAST CLOSE",
    }.get(kind, (kind or "unknown").upper())


def format_signal(signal: Dict[str, Any]) -> str:
    """Render one validated signal."""
    facts = signal.get("facts", {}) or {}
    calc = signal.get("calculated", {}) or {}
    ai = signal.get("ai", {}) or {}
    article = signal.get("article", {}) or {}

    direction = (signal.get("direction") or "LONG").upper()
    arrow = "🟢" if direction == "LONG" else "🔴"
    ticker = signal.get("ticker", "")
    company = signal.get("company_name") or ticker
    exchange = signal.get("exchange", "")

    lines: List[str] = []

    lines.append(f"<b>{arrow} {esc(company)}</b> ({esc(ticker)} · {esc(exchange)})")
    lines.append(f"<b>{direction}</b> · {esc(ai.get('event_type', 'OTHER').replace('_', ' ').title())}")

    if article.get("is_development"):
        lines.append("")
        lines.append("♻️ <i>New development in a story already covered</i>")

    # ---- market data (facts) --------------------------------------------
    lines.append("")
    lines.append("📊 <b>MARKET DATA</b> <i>(from market feed)</i>")
    price = facts.get("price")
    lines.append(
        f"   Price: <b>{_fmt(price)}</b> "
        f"<i>({_price_kind_label(facts.get('price_kind', ''))})</i>"
    )
    if facts.get("session_label"):
        lines.append(f"   Session: {esc(facts['session_label'])}")
    prev = facts.get("prev_close")
    if prev:
        change = facts.get("change_pct")
        arrow2 = "▲" if (change or 0) > 0 else ("▼" if (change or 0) < 0 else "—")
        lines.append(f"   Prev close: {_fmt(prev)}  {arrow2} {_fmt_num(change, 2, '%')}")
    if facts.get("market_cap_cr"):
        lines.append(f"   Market cap: {_fmt_num(facts['market_cap_cr'], 0, ' Cr')}")
    if facts.get("price_source"):
        lines.append(f"   Source: {esc(facts['price_source'])}")

    # ---- calculated levels ----------------------------------------------
    lines.append("")
    lines.append("🧮 <b>CALCULATED</b> <i>(computed from real prices)</i>")
    lines.append(f"   Entry:   <b>{_fmt(calc.get('entry'))}</b>")
    lines.append(f"   Target:  <b>{_fmt(calc.get('target'))}</b> "
                 f"<i>(+{_fmt_num(calc.get('reward_pct'), 1, '%')})</i>")
    lines.append(f"   Stop:    <b>{_fmt(calc.get('stop'))}</b> "
                 f"<i>(-{_fmt_num(calc.get('risk_pct'), 1, '%')})</i>")
    lines.append(f"   Risk/Reward: <b>{_fmt_num(calc.get('risk_reward'), 2)}x</b>")
    if calc.get("strategy"):
        lines.append(f"   Method: {esc(calc['strategy'])}")

    # Unavailable indicators are shown as "unavailable" rather than omitted:
    # silence would read as "nothing notable", which is a different claim.
    technical_bits = [
        f"RSI(14) {_fmt_num(calc['rsi_14'], 1) if calc.get('rsi_14') is not None else 'n/a'}",
        f"SMA20 {_fmt(calc['sma_20']) if calc.get('sma_20') is not None else 'n/a'}",
        f"ATR(14) {_fmt(calc['atr_14']) if calc.get('atr_14') is not None else 'n/a'}",
    ]
    if calc.get("trend"):
        technical_bits.append(f"trend {esc(calc['trend'].replace('_', ' '))}")
    if technical_bits:
        lines.append(f"   Technicals: {' · '.join(technical_bits)}")

    # ---- AI assessment ---------------------------------------------------
    lines.append("")
    lines.append("🤖 <b>AI ASSESSMENT</b> <i>(interpretation, not data)</i>")
    if ai.get("catalyst"):
        lines.append(f"   Catalyst: {esc(ai['catalyst'])}")
    if ai.get("thesis"):
        lines.append(f"   Thesis: {esc(ai['thesis'])}")
    if ai.get("watchpoint"):
        lines.append(f"   Watch: {esc(ai['watchpoint'])}")
    if ai.get("risk"):
        lines.append(f"   Risk: {esc(ai['risk'])}")
    confidence = signal.get("relevance_score")
    if confidence:
        lines.append(f"   Relevance: {int(confidence)}/100 <i>(model's own rating)</i>")

    # ---- provenance ------------------------------------------------------
    lines.append("")
    title = article.get("title", "")
    if title:
        lines.append(f"📰 {esc(title[:150])}")
    source = article.get("source", "")
    published = article.get("published_at", "")
    if source or published:
        bits = [esc(source)]
        if published:
            bits.append(esc(published[:16].replace("T", " ")))
        lines.append(f"   {' · '.join(bits)}")

    extra = article.get("corroborating_sources") or []
    if len(extra) > 1:
        lines.append(f"   Also reported by: {esc(', '.join(extra[:4]))}")

    url = article.get("url", "")
    if url:
        lines.append(f"   <a href='{esc_attr(url)}'>Read article</a>")

    lines.append("")
    lines.append(
        "<i>Market data is from the quote provider; levels are calculated by "
        "ATR/swing methods; AI text is interpretation only.</i>"
    )
    return "\n".join(lines)


def format_run_footer(sent: int, stats: Optional[Dict[str, Any]] = None) -> str:
    """Closing line for a run, so silence is always explained."""
    if sent <= 0:
        line = (
            "✅ Scan complete — <b>no qualifying new signals</b>.\n"
            "<i>Nothing met the bar: no genuinely new, material, verified stories "
            "with real market data. This is the correct outcome, not a failure.</i>"
        )
        if stats:
            line += (
                f"\n<i>{stats.get('articles_scraped', 0)} articles scanned · "
                f"{stats.get('articles_fresh', 0)} fresh · "
                f"{stats.get('articles_duplicate', 0)} already sent</i>"
            )
        return line
    body = f"✅ Sent <b>{sent}</b> signal{'s' if sent != 1 else ''}."
    if stats:
        scanned = stats.get("articles_scraped", 0)
        fresh = stats.get("articles_fresh", 0)
        dupes = stats.get("stories_duplicate", 0)
        body += (
            f"\n<i>{scanned} articles scanned · {fresh} fresh · "
            f"{dupes} already sent · max 3 per run</i>"
        )
    return body


def format_alert(title: str, message: str) -> str:
    return f"🚨 <b>{esc(title)}</b>\n\n{esc(message)}"


async def send_signal(signal: Dict[str, Any], bot_token: str, chat_id: int) -> bool:
    """Send one signal. Returns False instead of raising on failure."""
    from src.portfolio.telegram import send_message

    return await send_message(format_signal(signal), chat_id=chat_id)
