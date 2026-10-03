"""Production entry point for AlphaScout.

Run modes
---------
``run``      full pipeline; sends at most 3 signals to Telegram
``--dry-run`` runs everything except the Telegram send and prints what would
             have been sent. Also implies no state mutation for "sent".

The ordering below is the whole design in one place:

    1. verify our persistent store is reachable      (no memory -> no dedup)
    2. scrape news from configured sources
    3. pipeline: freshness -> dedup -> verified ticker -> real market data
                 -> AI assessment -> deterministic levels -> validation
    4. persist the rows
    5. send to Telegram, then mark as sent so it is never repeated
    6. flush state to durable storage
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IST = timezone(timedelta(hours=5, minutes=30), "IST")

from src.netfix import force_ipv4 as _force_ipv4_patch  # noqa: E402

_force_ipv4_patch()

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=os.getenv("ALPHASCOUT_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
for noisy in ("httpx", "aiohttp", "urllib3", "yfinance", "peewee"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

logger = logging.getLogger("alphascout")

MAX_SIGNALS_PER_RUN = 3

# Set by `main.py scan` to restrict candidates to screener-flagged tickers.
# ``None`` means no restriction (the default for `run`).
TICKER_ALLOWLIST: set | None = None


def _banner(mode: str, dry_run: bool) -> None:
    label = "DRY RUN (no Telegram)" if dry_run else mode.upper()
    print()
    print("=" * 66)
    print(f"  ALPHASCOUT  ·  {label}")
    print(f"  {datetime.now(IST):%Y-%m-%d %H:%M:%S} IST")
    print(f"  Max {MAX_SIGNALS_PER_RUN} signals per run · quality over quota")
    print("=" * 66)


async def run(
    *,
    dry_run: bool = False,
    max_signals: int = MAX_SIGNALS_PER_RUN,
    freshness_hours: int = 30,
    use_cache: bool = False,
    send: bool = True,
) -> dict:
    """One full pipeline execution. Returns a run report."""
    from src.config import validate_api_keys
    from src.market.session import market_status
    from src.pipeline.news_signal import NewsSignalPipeline
    from src.store import get_store

    report: dict = {"dry_run": dry_run, "sent": [], "signals": [], "errors": []}

    # --- 1. persistent store -------------------------------------------
    store = get_store()
    healthy, detail = store.health_check()
    if not healthy:
        # Without durable memory the run cannot deduplicate, which is the one
        # thing it must not get wrong. Refuse rather than spam.
        logger.error("PERSISTENT STORE UNAVAILABLE (%s): %s", store.name, detail)
        logger.error("Refusing to run: dedup requires durable state.")
        report["errors"].append(f"store unavailable: {detail}")
        return report
    logger.info("Persistent store: %s (%s)", store.name, detail)
    logger.info("Store contents: %s", store.counts())

    # --- 2. keys --------------------------------------------------------
    keys = validate_api_keys()
    missing = [k for k, v in keys.items() if k != "details" and not v]
    logger.info("API keys present: %s", ", ".join(sorted(missing and [] or
                [k for k, v in keys.items() if k != "details" and v])))
    if not keys.get("groq"):
        logger.error("No Groq API key - cannot assess news. Aborting.")
        report["errors"].append("no groq key")
        return report

    # --- 3. market context ----------------------------------------------
    session = market_status()
    logger.info("Market: %s - %s", session.session, session.label)

    # --- 4. scrape -------------------------------------------------------
    from src.scraping.scraper import scrape_all_sources

    logger.info("Scraping news sources...")
    articles = scrape_all_sources(use_cache=use_cache)
    logger.info("Scraped %d articles", len(articles))
    if not articles:
        logger.warning("No articles retrieved")
        store.flush()
        return report

    # --- 5. pipeline -----------------------------------------------------
    pipeline = NewsSignalPipeline(
        store,
        freshness_hours=freshness_hours,
        max_signals=max_signals,
        ticker_allowlist=TICKER_ALLOWLIST,
    )
    signals = pipeline.run(articles)
    report["signals"] = [
        {
            "ticker": s["ticker"],
            "company": s.get("company_name"),
            "direction": s.get("direction"),
            "price": s["facts"].get("price"),
            "price_kind": s["facts"].get("price_kind"),
            "entry": s["calculated"].get("entry"),
            "target": s["calculated"].get("target"),
            "stop": s["calculated"].get("stop"),
            "risk_reward": s["calculated"].get("risk_reward"),
            "rsi_14": s["calculated"].get("rsi_14"),
            "article": s["article"].get("title"),
            "source": s["article"].get("source"),
        }
        for s in signals
    ]
    report["stats"] = pipeline.stats.as_dict()

    # --- 6. persist BEFORE sending --------------------------------------
    # A dry run must leave no trace: persisting here would create cooldown
    # entries and history rows for messages the user never received.
    if signals and not dry_run:
        pipeline.persist(signals)

    if not signals:
        logger.info("No qualifying signals this run - nothing will be sent")
        store.flush()
        _print_empty_summary(pipeline.stats)
        return report

    # --- 7. send ---------------------------------------------------------
    if dry_run or not send:
        logger.info("DRY RUN: %d signal(s) would be sent", len(signals))
        _print_signals(signals)
        store.flush()
        return report

    ok = await _send(signals, pipeline, store)
    report["sent"] = [s["ticker"] for s in signals if s.get("_sent")]
    logger.info("Delivered %d/%d signal(s)", len(report["sent"]), len(signals))

    store.flush()
    return report


async def _send(signals: list, pipeline, store) -> bool:
    """Send signals, marking each one sent only after Telegram confirms."""
    from src.portfolio.formatter import format_run_footer, format_signal
    from src.portfolio.telegram import send_message

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    raw_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not raw_chat:
        logger.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set - cannot send")
        return False
    try:
        chat_id = int(raw_chat)
    except ValueError:
        logger.error("TELEGRAM_CHAT_ID is not an integer")
        return False

    delivered = []
    for signal in signals:
        message = format_signal(signal)
        try:
            sent = await send_message(message, chat_id=chat_id)
        except Exception as exc:
            logger.error("Telegram raised for %s: %s", signal["ticker"], exc)
            sent = False
        if sent:
            signal["_sent"] = True
            delivered.append(signal)
            logger.info("Sent %s to Telegram", signal["ticker"])
        else:
            logger.error("Telegram delivery FAILED for %s - not marked as sent", signal["ticker"])

    try:
        await send_message(
            format_run_footer(len(delivered), pipeline.stats.as_dict()), chat_id=chat_id
        )
    except Exception as exc:
        logger.warning("Could not send run footer: %s", exc)

    if delivered:
        pipeline.mark_sent(delivered)
    return len(delivered) == len(signals)


def _print_signals(signals: list) -> None:
    from src.portfolio.formatter import format_signal

    for signal in signals:
        print()
        print("-" * 66)
        print(format_signal(signal))


def _print_empty_summary(stats) -> None:
    print()
    print("-" * 66)
    print("No qualifying new signals.")
    print(f"  scanned={stats.articles_scraped} fresh={stats.articles_fresh} "
          f"stale={stats.articles_stale} duplicate={stats.stories_duplicate} "
          f"unavailable_market_data={stats.market_unavailable}")


def show_state() -> None:
    from src.store import get_store

    store = get_store()
    print(f"Backend: {store.name}")
    print(f"Health : {store.health_check()}")
    print(f"Counts : {store.counts()}")
    sent = store.sent_story_keys()
    print(f"Sent stories: {len(sent)}")
    for signal in store.recent_signals(days=7, limit=10):
        print(f"  {signal.generated_at[:19]}  {signal.ticker:14} "
              f"price={signal.market_price:<10} sent={signal.sent}  {signal.article_title[:50]}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AlphaScout news-to-signal pipeline")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "state", "health"])
    parser.add_argument("--dry-run", action="store_true",
                        help="run everything but do not send Telegram messages")
    parser.add_argument("--max-signals", type=int, default=MAX_SIGNALS_PER_RUN,
                        help=f"cap on signals per run (hard max {MAX_SIGNALS_PER_RUN})")
    parser.add_argument("--freshness-hours", type=int, default=30,
                        help="reject articles published longer ago than this")
    parser.add_argument("--use-cache", action="store_true",
                        help="reuse cached articles instead of scraping fresh")
    args = parser.parse_args(argv)

    if args.command == "state":
        show_state()
        return 0

    if args.command == "health":
        from src.config import validate_api_keys
        from src.market.session import market_status
        from src.store import get_store

        store = get_store()
        print(f"store: {store.name} -> {store.health_check()}")
        print(f"counts: {store.counts()}")
        keys = validate_api_keys()
        for key, value in sorted(keys.items()):
            if key == "details":
                continue
            print(f"  {'OK ' if value else 'MISSING'} {key}")
        status = market_status()
        print(f"market: {status.session} - {status.label}")
        return 0 if store.health_check()[0] else 1

    dry = args.dry_run
    _banner(args.command, dry)
    report = asyncio.run(run(
        dry_run=dry,
        max_signals=args.max_signals,
        freshness_hours=args.freshness_hours,
        use_cache=args.use_cache,
    ))

    if dry and report.get("signals"):
        print()
        print("=" * 66)
        print(f"  DRY RUN: {len(report['signals'])} signal(s) would have been sent")
        print("=" * 66)

    return 0


__all__ = ["run", "main", "show_state"]
