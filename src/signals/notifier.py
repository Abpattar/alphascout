"""
Signal Notifier
Sends alerts via Terminal + Telegram + JSON log
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from src.portfolio.telegram import send_signal, send_portfolio, send_alert

logger = logging.getLogger(__name__)

SIGNALS_LOG = Path(__file__).parent.parent.parent / "data" / "signals_log.jsonl"


class Notifier:
    """Multi-channel signal notification"""

    def __init__(self):
        self.last_alerts = {}

    def send_signals(self, signals: List[Dict], executed: List[Dict]):
        """Send signals to all channels"""
        for signal in executed:
            status = signal.get("status", "MANUAL_ALERT")
            trade = signal.get("trade", {})
            ticker = signal.get("prediction", {}).get("ticker", "").replace(".NS", "")

            # Terminal output
            self._print_terminal(signal, status)

            # Telegram
            if status == "AUTO_EXECUTED":
                import asyncio
                asyncio.create_task(send_signal(signal))
            elif status == "MANUAL_ALERT":
                import asyncio
                asyncio.create_task(send_signal(signal))

            # JSON log
            self._log_signal(signal)

    def _print_terminal(self, signal: Dict, status: str):
        """Print formatted signal to terminal"""
        trade = signal.get("trade", {})
        catalyst = signal.get("catalyst", {})
        article = signal.get("article", {})

        trade_type = trade.get("trade_type", "BUY")
        ticker = signal.get("prediction", {}).get("ticker", "").replace(".NS", "")
        name = trade.get("name", "")

        # Status badge
        if status == "AUTO_EXECUTED":
            badge = "🤖 AUTO"
        elif status == "AUTO_FAILED":
            badge = "❌ AUTO-FAIL"
        else:
            badge = "📋 MANUAL"

        confidence = trade.get("confidence", 0)
        rr = trade.get("risk_reward_ratio", 0)
        target = trade.get("target_pct", 0)
        stop = trade.get("stop_loss_pct", 0)

        print(f"\n{'═' * 70}")
        print(f" {badge}  {trade_type}  |  {name} ({ticker})  |  Conf: {confidence}%  |  R:R {rr:.1f}x")
        print(f"{'─' * 70}")
        print(f" 📰 {article.get('title', '')[:100]}")
        print(f"   Source: {article.get('source', '')} | {catalyst.get('type', '')} ({catalyst.get('timeframe', '')})")
        print(f"")
        print(f" 💰 Entry: {trade.get('entry_strategy', '')}")
        print(f" 🎯 Target: {trade.get('target_price', '')}  (+{target}%)")
        print(f" 🛑 Stop: {trade.get('stop_loss_price', '')}  (-{stop}%)")
        print(f" ⏱  Hold: {trade.get('hold_days', 0)}-{trade.get('max_hold_days', 0)} days")
        print(f"")
        print(f" 💡 {trade.get('thesis_one_line', '')}")
        print(f" ⚠️ Kill: {trade.get('kill_switch', '')}")
        print(f" 🔗 {article.get('url', '')}")
        print(f"{'═' * 70}\n")

    def _log_signal(self, signal: Dict):
        """Log signal to JSONL file"""
        try:
            with open(SIGNALS_LOG, "a") as f:
                f.write(json.dumps(signal, default=str) + "\n")
        except Exception as e:
            logger.warning(f"Signal log failed: {e}")

    def send_portfolio_update(self):
        """Send portfolio summary"""
        import asyncio
        asyncio.create_task(send_portfolio({}))  # Will be filled by portfolio manager

    def send_emergency_alert(self, message: str):
        """Send urgent alert"""
        import asyncio
        asyncio.create_task(send_alert(message))
        print(f"\n🚨 EMERGENCY ALERT: {message}\n")


# Backward compatibility
async def notify_signal(signal: Dict):
    await send_signal(signal)