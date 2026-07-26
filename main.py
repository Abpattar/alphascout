#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlphaScout - Multi-Sector Small-Cap News -> Trade Signal Bot
Main Entry Point
"""
import asyncio
import logging
import os
import sys

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
from datetime import datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Load .env if exists
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        ALPHASCOUT v1.0                                       ║
║         Multi-Sector Small-Cap News → Trade Signal Bot                       ║
║         Price: ₹50-500 | Cap: ₹100-5000Cr | Horizon: 3-7 days               ║
║         Auto-Execute @ 90%+ Confidence | Risk: 3% per trade                 ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)


async def run_pipeline(use_cache: bool = True, max_signals: int = 5) -> list:
    """Run the full analysis pipeline"""
    from src.scraping.scraper import scrape_all_sources
    from src.analysis.pipeline import analyze_articles
    from src.config import validate_api_keys, get_signals_config

    # Validate API keys
    keys = validate_api_keys()
    print("\n🔑 API Key Status:")
    for k, v in keys.items():
        if k != "details":
            status = "✅" if v else "❌"
            print(f"   {status} {k}")

    if not keys.get("groq"):
        print("\n❌ No Groq API key found! Run setup_credentials.py first")
        return []

    print("\n📡 Scraping news sources...")
    articles = scrape_all_sources(use_cache=use_cache)
    print(f"   Found {len(articles)} relevant articles")

    if not articles:
        print("   No articles found. Try running without cache.")
        return []

    print("\n🧠 Running AI analysis pipeline...")
    signals = analyze_articles(articles, max_signals=max_signals)

    # Send signals to Telegram
    if signals:
        try:
            from src.portfolio.telegram import send_signal
            for s in signals:
                await send_signal(s)
        except Exception as e:
            logging.warning(f"Telegram send failed: {e}")

    # Print results
    if signals:
        print(f"\n🎯 TOP {len(signals)} SIGNALS:")
        print("=" * 80)
        for i, s in enumerate(signals, 1):
            t = s["trade"]
            print(f"\n#{i} {t['name']} [{t['ticker']}] — {t['trade_type']} ({t['direction']})")
            print(f"   📰 {s['article']['title'][:80]}")
            print(f"   🎯 Target: +{t['target_pct']}% | Stop: -{t['stop_loss_pct']}% | R:R {t['risk_reward_ratio']:.1f}x")
            print(f"   💰 Entry: {t['entry_strategy']}")
            print(f"   📊 Confidence: {t['confidence']}% | Hold: {t['hold_days']} days")
            print(f"   🧠 Ensemble: {'YES' if s.get('ensemble_agreement') else 'NO'}")
            print(f"   ⚡ Auto-Execute: {'YES' if t['confidence'] >= 90 else 'NO (manual review)'}")
    else:
        print("\n⚠️  No qualifying signals found today")

    return signals


async def run_screener_pipeline(use_cache: bool = True, max_signals: int = 5) -> list:
    """Screener-first: find active small-caps, then search for news about them"""
    from src.screening.screener import scan_for_active_smallcaps
    from src.scraping.scraper import scrape_all_sources
    from src.analysis.pipeline import analyze_with_screener
    from src.config import validate_api_keys

    # Validate API keys
    keys = validate_api_keys()
    print("\n🔑 API Key Status:")
    for k, v in keys.items():
        if k != "details":
            status = "✅" if v else "❌"
            print(f"   {status} {k}")

    if not keys.get("groq"):
        print("\n❌ No Groq API key found! Run setup_credentials.py first")
        return []

    # Step 1: Screen for active small-caps
    print("\n🔍 Step 1: Screening for active small-caps...")
    candidates = scan_for_active_smallcaps(max_results=20)
    print(f"   Found {len(candidates)} screener candidates")

    if candidates:
        print("\n   Top candidates:")
        for c in candidates[:10]:
            print(f"   {c.ticker:15s} | ₹{c.price:8.2f} | {c.change_pct:+6.1f}% | {c.reason}")

    # Step 2: Scrape news
    print("\n📡 Step 2: Scraping news sources...")
    articles = scrape_all_sources(use_cache=use_cache)
    print(f"   Found {len(articles)} articles")

    if not articles:
        print("   No articles found.")
        return []

    # Step 3: Match candidates to articles and analyze
    print("\n🧠 Step 3: Analyzing matched articles...")
    candidate_dicts = [c.to_dict() for c in candidates]
    signals = analyze_with_screener(candidate_dicts, articles, max_signals=max_signals)

    # Send signals to Telegram
    if signals:
        try:
            from src.portfolio.telegram import send_signal
            for s in signals:
                await send_signal(s)
        except Exception as e:
            logging.warning(f"Telegram send failed: {e}")

    # Print results
    if signals:
        print(f"\n🎯 TOP {len(signals)} SIGNALS (screener-first):")
        print("=" * 80)
        for i, s in enumerate(signals, 1):
            t = s["trade"]
            print(f"\n#{i} {t['name']} [{t['ticker']}] — {t['trade_type']} ({t['direction']})")
            print(f"   📰 {s['article']['title'][:80]}")
            print(f"   🎯 Target: +{t['target_pct']}% | Stop: -{t['stop_loss_pct']}% | R:R {t['risk_reward_ratio']:.1f}x")
            print(f"   💰 Entry: {t['entry_strategy']}")
            print(f"   📊 Confidence: {t['confidence']}% | Hold: {t['hold_days']} days")
            print(f"   🧠 Ensemble: {'YES' if s.get('ensemble_agreement') else 'NO'}")
            print(f"   ⚡ Auto-Execute: {'YES' if t['confidence'] >= 90 else 'NO (manual review)'}")
    else:
        print("\n⚠️  No qualifying signals found")
        print("   The screener found candidates but no matching news articles.")
        print("   Try running again later or check if news sources are accessible.")

    return signals


def run_scheduler():
    """Run 2x daily scheduler"""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

    async def scheduled_run():
        print(f"\n⏰ Scheduled run at {datetime.now().strftime('%H:%M:%S')}")
        await run_pipeline(use_cache=False, max_signals=5)

    # 6:30 AM and 4:30 PM IST
    scheduler.add_job(scheduled_run, CronTrigger(hour=6, minute=30, timezone="Asia/Kolkata"))
    scheduler.add_job(scheduled_run, CronTrigger(hour=16, minute=30, timezone="Asia/Kolkata"))

    scheduler.start()
    print("\n⏰ Scheduler started (6:30 AM & 4:30 PM IST)")
    print("   Press Ctrl+C to stop\n")

    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        scheduler.shutdown()
        print("\n👋 Scheduler stopped")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="AlphaScout - News to Trade Signal Bot")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "scan", "scheduler", "backtest", "portfolio", "config", "test", "db"],
                        help="Command to execute")
    parser.add_argument("--cache", action="store_true", default=True,
                        help="Use cached articles")
    parser.add_argument("--no-cache", dest="cache", action="store_false",
                        help="Force fresh scrape")
    parser.add_argument("--signals", type=int, default=5,
                        help="Max signals to return")
    parser.add_argument("--setup", action="store_true",
                        help="Run credential setup wizard")

    args = parser.parse_args()

    print_banner()

    if args.setup:
        from scripts.setup_credentials import main as setup_main
        setup_main()
        return

    if args.command == "run":
        await run_pipeline(use_cache=args.cache, max_signals=args.signals)

    elif args.command == "scan":
        await run_screener_pipeline(use_cache=args.cache, max_signals=args.signals)

    elif args.command == "scheduler":
        run_scheduler()

    elif args.command == "backtest":
        sys.path.insert(0, str(Path(__file__).parent / "scripts"))
        from backtest import main as backtest_main
        backtest_main()

    elif args.command == "portfolio":
        from src.portfolio.manager import PortfolioManager
        pm = PortfolioManager()
        print("\n📊 CURRENT PORTFOLIO:")
        for p in pm.positions.values():
            print(f"   {p.ticker} | {p.quantity} @ ₹{p.entry_price} | "
                  f"SL: ₹{p.stop_loss} | Target: ₹{p.target} | "
                  f"Days: {p.days_held()}/{p.max_hold_days}")

    elif args.command == "config":
        from src.config import load_settings
        import json
        settings = load_settings()
        print(json.dumps(settings, indent=2))

    elif args.command == "test":
        # Quick integration test
        from src.ai.providers import get_registry
        registry = get_registry()
        stats = registry.get_all_stats()
        print("\n📊 Provider Stats:")
        for name, stat in stats.items():
            if "providers" in stat:
                # Multi-key provider (Groq)
                total_calls = sum(p.get("calls", 0) for p in stat["providers"])
                total_errors = sum(p.get("errors", 0) for p in stat["providers"])
                print(f"   {name}: {total_calls} calls, {total_errors} errors, {stat.get('keys', '?')} keys")
            elif "calls" in stat:
                print(f"   {name}: {stat['calls']} calls, {stat['errors']} errors, {stat['success_rate']}% success")
            else:
                print(f"   {name}: {stat}")

    elif args.command == "db":
        from src.storage.db import get_db
        db = get_db()
        stats = db.get_stats()
        print("\n📊 DATABASE STATS:")
        print(f"   Articles stored:      {stats['articles']}")
        print(f"   LLM analyses:         {stats['llm_analyses']}")
        print(f"   Signals generated:    {stats['signals']}")
        print(f"   Outcomes recorded:    {stats['outcomes']}")
        print(f"   Wins:                 {stats['wins']}")
        print(f"   Losses:               {stats['losses']}")
        print(f"   Win rate:             {stats['win_rate']}%")
        print(f"\n   DB path: {db.db_path}")

        unresolved = db.get_unresolved_signals(days=14)
        if unresolved:
            print(f"\n   ⏳ Unresolved signals (last 14 days): {len(unresolved)}")
            for s in unresolved[:5]:
                print(f"      {s['signal_id'][:30]} | {s['ticker']} | conf={s['confidence']}%")


if __name__ == "__main__":
    asyncio.run(main())