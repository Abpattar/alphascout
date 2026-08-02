#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlphaScout - Multi-Sector Small-Cap News -> Trade Signal Bot
Main Entry Point
"""
import asyncio
import json
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
    from src.ai.providers import reset_run_stats, print_run_stats

    reset_run_stats()  # Problem 10: track per-run usage

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
            cal_conf = s.get("calibrated_confidence", t['confidence'])
            auto_exec = s.get("auto_execute", t['confidence'] >= 90)
            print(f"\n#{i} {t['name']} [{t['ticker']}] — {t['trade_type']} ({t['direction']})")
            print(f"   📰 {s['article']['title'][:80]}")
            print(f"   🎯 Target: +{t['target_pct']}% | Stop: -{t['stop_loss_pct']}% | R:R {t['risk_reward_ratio']:.1f}x")
            print(f"   💰 Entry: {t['entry_strategy']}")
            print(f"   📊 Confidence: {t['confidence']}% (calibrated: {cal_conf:.0f}%) | Hold: {t['hold_days']} days")
            print(f"   🧠 Ensemble: {'YES' if s.get('ensemble_agreement') else 'NO'}")
            print(f"   ⚡ Auto-Execute: {'YES' if auto_exec else 'NO (manual review)'}")
            print(f"   ℹ️  {s.get('auto_execute_reason', '')}")
            if s.get("implied_beneficiary"):
                print(f"   🔎 Implied beneficiary: company NOT named in news (inferred via research)")
            rel = (s.get("relation") or "").strip()
            print(f"   🏭 {s['stock'].get('sector_display', s['stock'].get('sector', '?'))}" + (f" | {rel}" if rel else ""))
            if s.get("stock", {}).get("newly_added"):
                print(f"   🆕 Newly discovered company — added to universe on the fly")
    else:
        print("\n⚠️  No qualifying signals found today")

    print_run_stats()  # Problem 10: print per-run usage
    return signals


async def run_screener_pipeline(use_cache: bool = True, max_signals: int = 5) -> list:
    """Screener-first: find active small-caps, then search for news about them.
    Problem 4: Price/volume spikes as main trigger, news as confirmation."""
    from src.screening.screener import scan_for_active_smallcaps, scan_price_volume_spikes
    from src.universe.builder import get_universe
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

    # Step 1a: Check for price/volume spikes (Problem 4: primary trigger)
    print("\n🔍 Step 1: Scanning for price/volume spikes...")
    universe = get_universe()
    universe_tickers = list(universe.keys())
    spike_candidates = scan_price_volume_spikes(universe_tickers, max_results=15)
    print(f"   Found {len(spike_candidates)} stocks with unusual activity")

    # Step 1b: Also scan NSE gainers / Screener.in / Trendlyne
    print("\n🔍 Step 1b: Screening NSE/Screener/Trendlyne...")
    screener_candidates = scan_for_active_smallcaps(max_results=20)
    print(f"   Found {len(screener_candidates)} screener candidates")

    # Combine candidates (spikes take priority)
    all_candidates = []
    seen_tickers = set()
    for c in spike_candidates + screener_candidates:
        if c.ticker not in seen_tickers:
            seen_tickers.add(c.ticker)
            all_candidates.append(c)

    if all_candidates:
        print("\n   Top candidates:")
        for c in all_candidates[:10]:
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
    candidate_dicts = [c.to_dict() for c in all_candidates]
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
            cal_conf = s.get("calibrated_confidence", t['confidence'])
            auto_exec = s.get("auto_execute", t['confidence'] >= 90)
            print(f"\n#{i} {t['name']} [{t['ticker']}] — {t['trade_type']} ({t['direction']})")
            print(f"   📰 {s['article']['title'][:80]}")
            print(f"   🎯 Target: +{t['target_pct']}% | Stop: -{t['stop_loss_pct']}% | R:R {t['risk_reward_ratio']:.1f}x")
            print(f"   💰 Entry: {t['entry_strategy']}")
            print(f"   📊 Confidence: {t['confidence']}% (calibrated: {cal_conf:.0f}%) | Hold: {t['hold_days']} days")
            print(f"   🧠 Ensemble: {'YES' if s.get('ensemble_agreement') else 'NO'}")
            print(f"   ⚡ Auto-Execute: {'YES' if auto_exec else 'NO (manual review)'}")
            print(f"   ℹ️  {s.get('auto_execute_reason', '')}")
            if s.get("implied_beneficiary"):
                print(f"   🔎 Implied beneficiary: company NOT named in news (inferred via research)")
            rel = (s.get("relation") or "").strip()
            print(f"   🏭 {s['stock'].get('sector_display', s['stock'].get('sector', '?'))}" + (f" | {rel}" if rel else ""))
            if s.get("stock", {}).get("newly_added"):
                print(f"   🆕 Newly discovered company — added to universe on the fly")
    else:
        print("\n⚠️  No qualifying signals found")
        print("   The screener found candidates but no matching news articles.")
        print("   Try running again later or check if news sources are accessible.")

    print_run_stats()  # Problem 10: print per-run usage
    return signals


# ── Issue 2: Lightweight intra-day spike scan ─────────────────────────────────
_SPIKE_QUEUE_PATH = ROOT / "data" / "spike_queue.json"


def _load_spike_queue() -> list:
    try:
        if _SPIKE_QUEUE_PATH.exists():
            with open(_SPIKE_QUEUE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_spike_queue(queue: list):
    _SPIKE_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_SPIKE_QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def _enqueue_spike_tickers(candidates: list):
    """Add newly-discovered spiking tickers to the queue (deduped)."""
    queue = _load_spike_queue()
    seen = {item["ticker"] for item in queue}
    for c in candidates:
        if c.ticker not in seen:
            queue.append(c.to_dict())
            seen.add(c.ticker)
    _save_spike_queue(queue)


async def run_spike_mini():
    """Issue 2: Lightweight scan — scrape only queued tickers, mini-analyse, send signals."""
    from src.screening.screener import scan_price_volume_spikes
    from src.universe.builder import get_universe
    from src.scraping.scraper import scrape_all_sources
    from src.analysis.pipeline import analyze_with_screener
    from src.config import validate_api_keys
    from src.ai.providers import reset_run_stats, print_run_stats

    keys = validate_api_keys()
    if not keys.get("groq"):
        return

    reset_run_stats()

    # Step 1: scan universe for new spikes and enqueue
    universe = get_universe()
    spike_candidates = scan_price_volume_spikes(list(universe.keys()), max_results=10)
    if spike_candidates:
        _enqueue_spike_tickers(spike_candidates)
        print(f"   Enqueued {len(spike_candidates)} new spike tickers")

    # Step 2: load queue and scrape news
    queue = _load_spike_queue()
    if not queue:
        print("   Spike queue empty, skipping")
        return

    articles = scrape_all_sources(use_cache=True)
    if not articles:
        print("   No articles found")
        return

    # Step 3: match queued tickers to articles (lightweight)
    queue_tickers = {item["ticker"] for item in queue}
    matched_articles = []
    for article in articles:
        text = ""
        if hasattr(article, 'to_dict'):
            d = article.to_dict()
            text = f"{d.get('title', '')} {d.get('content', '')[:1000]}"
        elif isinstance(article, dict):
            text = f"{article.get('title', '')} {article.get('content', '')[:1000]}"
        text_lower = text.lower()
        for tk in queue_tickers:
            base = tk.replace(".NS", "").replace(".BO", "").lower()
            if len(base) >= 4 and base in text_lower:
                matched_articles.append(article)
                break

    if not matched_articles:
        print(f"   No articles matched {len(queue_tickers)} queued tickers")
        return

    print(f"   Matched {len(matched_articles)} articles for {len(queue_tickers)} queued tickers")
    candidate_dicts = [item for item in queue]
    signals = analyze_with_screener(candidate_dicts, matched_articles, max_signals=3)

    if signals:
        try:
            from src.portfolio.telegram import send_signal
            for s in signals:
                await send_signal(s)
        except Exception as e:
            logging.warning(f"Telegram send failed: {e}")

        for s in signals:
            t = s["trade"]
            print(f"   ⚡ {t['name']} [{t['ticker']}] — {t['trade_type']} ({t['direction']}) conf={t['confidence']}%")

    # Clean processed tickers from queue
    signaled_tickers = {s["trade"]["ticker"] for s in signals} if signals else set()
    remaining = [item for item in queue if item["ticker"] not in signaled_tickers]
    _save_spike_queue(remaining)

    print_run_stats()


def run_scheduler():
    """Run 2x daily scheduler with intra-day spike scanning (Issue 2) and auto-outcome resolution (Problem 11)"""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from src.config import load_settings

    settings = load_settings()
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    spike_interval = settings.get("schedule", {}).get("spike_scan_interval_minutes", 15)

    async def scheduled_run():
        print(f"\n⏰ Scheduled run at {datetime.now().strftime('%H:%M:%S')}")
        await run_pipeline(use_cache=False, max_signals=5)

    async def scheduled_spike_scan():
        """Issue 2: Lightweight spike scan — find spiking tickers and queue them for mini-analysis."""
        from datetime import datetime as dt
        now = dt.now()
        ist_hour = (now.hour + 5) % 24  # rough IST offset (no pytz needed)
        ist_minute = now.minute
        market_open = ist_hour > 9 or (ist_hour == 9 and ist_minute >= 15)
        market_closed = ist_hour >= 15 and ist_minute >= 30

        if not market_open or market_closed:
            return  # skip outside market hours

        print(f"\n⚡ Spike scan at {now.strftime('%H:%M:%S')} IST")
        await run_spike_mini()

    async def scheduled_resolve_outcomes():
        """Problem 11: Auto-check signal outcomes a few days after generation."""
        print(f"\n🔄 Auto-resolving signal outcomes at {datetime.now().strftime('%H:%M:%S')}")
        try:
            from scripts.backtest import resolve_outcomes
            result = resolve_outcomes(days=7)
            print(f"   Resolved: {result.get('resolved', 0)} signals")

            # Re-calibrate after resolving outcomes
            from src.analysis.calibration import get_calibrator
            calibrator = get_calibrator()
            calibrator.calibrate_from_db()
            print("   Recalibrated confidence from new outcomes")
        except Exception as e:
            print(f"   Outcome resolution failed: {e}")

    # 6:30 AM and 4:30 PM IST — main runs
    scheduler.add_job(scheduled_run, CronTrigger(hour=6, minute=30, timezone="Asia/Kolkata"))
    scheduler.add_job(scheduled_run, CronTrigger(hour=16, minute=30, timezone="Asia/Kolkata"))

    # Issue 2: Spike scan every N minutes during market hours (9:15 AM – 3:30 PM IST)
    scheduler.add_job(
        scheduled_spike_scan,
        IntervalTrigger(minutes=spike_interval),
        id="spike_scan",
        name=f"Spike scan every {spike_interval} min",
    )

    # Problem 11: Auto-check outcomes at 9:30 AM IST (after market opens, check previous signals)
    scheduler.add_job(scheduled_resolve_outcomes, CronTrigger(hour=9, minute=30, timezone="Asia/Kolkata"))

    scheduler.start()
    print("\n⏰ Scheduler started:")
    print("   Main runs: 6:30 AM & 4:30 PM IST")
    print(f"   Spike scan: every {spike_interval} min during market hours (9:15 AM – 3:30 PM IST)")
    print("   Auto-outcome resolution: 9:30 AM IST (Problem 11)")
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
                        choices=["run", "scan", "scheduler", "backtest", "portfolio", "config", "test", "db", "calibrate"],
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

    # Problem 9 + Issue 3: Personal-use-only guardrail — hard gate when sharing is enabled
    from src.config import load_settings
    _settings = load_settings()
    if not _settings.get("portfolio", {}).get("personal_use_only", True):
        # Issue 3: require env-var acknowledgement before allowing non-personal mode
        if not os.environ.get("I_HAVE_REVIEWED_SEBI_REGULATIONS"):
            print("\n🚫 BLOCKED: personal_use_only is FALSE in settings.yaml")
            print("   Sharing trade signals publicly requires SEBI Research Analyst registration.")
            print("   To acknowledge this and continue, set the environment variable:")
            print("     I_HAVE_REVIEWED_SEBI_REGULATIONS=true")
            print("   Then re-run the command.")
            print("   Aborting.\n")
            sys.exit(1)
        print("\n⚠️  SEBI ACKNOWLEDGED: personal_use_only is False — running in shared mode")
        print("   You are responsible for SEBI compliance.\n")

    if args.command == "run":
        await run_pipeline(use_cache=args.cache, max_signals=args.signals)

    elif args.command == "scan":
        await run_screener_pipeline(use_cache=args.cache, max_signals=args.signals)

    elif args.command == "scheduler":
        run_scheduler()

    elif args.command == "backtest":
        # Problem 6: Actually run backtest — resolve outcomes first, then show results
        sys.path.insert(0, str(Path(__file__).parent / "scripts"))
        from scripts.backtest import resolve_outcomes, show_results

        print("\n📊 RUNNING BACKTEST...")
        print("Step 1: Resolving signal outcomes from yfinance...")
        resolve_outcomes(days=30)
        print("\nStep 2: Computing backtest metrics...")
        results = show_results()

        if not results:
            print("\n💡 No outcomes yet. Run the pipeline a few times to generate signals,")
            print("   then run backtest again to see results.")
            print("\n   python main.py run --signals 3   # Generate signals")
            print("   python main.py backtest           # Check outcomes (after a few days)")

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

    elif args.command == "calibrate":
        from src.analysis.calibration import get_calibrator
        calibrator = get_calibrator()
        print("\n🔄 Recalibrating from stored outcomes...")
        calibrator.calibrate_from_db()
        print(calibrator.get_calibration_report())


if __name__ == "__main__":
    asyncio.run(main())