#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AlphaScout - Indian market news to validated trade signals.

Single production entry point. The previous version of this file carried a
second, parallel pipeline (``legacy-run``) whose trade prices and technical
indicators were written by the language model. That path has been removed
rather than left reachable, because running it would publish invented numbers.

Commands
--------
  run         full pipeline; sends at most 3 signals to Telegram
  scan        as `run`, but restricted to stocks a live screener flags
  state       show persistent store contents
  health      check store, credentials and market session
  backtest    resolve historical signal outcomes
  db          database-style statistics
  holds       manual buy/sell tracking
  calibrate   recalibrate confidence from resolved outcomes
  config      print effective settings
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IST = timezone(timedelta(hours=5, minutes=30), "IST")

from src.netfix import force_ipv4 as _force_ipv4_patch  # noqa: E402

_force_ipv4_patch()

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover - optional dependency
    pass

logging.basicConfig(
    level=os.getenv("ALPHASCOUT_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
for _noisy in ("httpx", "aiohttp", "urllib3", "yfinance", "peewee"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

logger = logging.getLogger("alphascout")

# Hard ceiling from the product requirement. Never exceeded, in any mode.
MAX_SIGNALS_PER_RUN = 3


def print_banner(mode: str) -> None:
    print()
    print("=" * 68)
    print("  ALPHASCOUT  ·  INDIAN MARKET SIGNAL SCANNER")
    print(f"  mode={mode}   {datetime.now(IST):%Y-%m-%d %H:%M:%S} IST")
    print(f"  max {MAX_SIGNALS_PER_RUN} signals/run · quality over quota · no invented numbers")
    print("=" * 68)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_state() -> int:
    from src.pipeline.runner import show_state

    show_state()
    return 0


def cmd_health() -> int:
    from src.config import validate_api_keys
    from src.market.session import market_status
    from src.store import get_store

    ok = True
    store = get_store()
    healthy, detail = store.health_check()
    print(f"store          : {store.name} -> {'OK' if healthy else 'UNAVAILABLE'} ({detail})")
    ok = ok and healthy
    try:
        print(f"store contents : {store.counts()}")
    except Exception as exc:
        print(f"store contents : unavailable ({exc})")
        ok = False

    keys = validate_api_keys()
    for key, value in sorted(keys.items()):
        if key == "details":
            continue
        print(f"  {'OK     ' if value else 'MISSING'} {key}")
    if not keys.get("groq"):
        ok = False

    status = market_status()
    print(f"market session : {status.session} - {status.label}")
    print(f"price kind     : {status.price_kind}")

    # AI providers are probed for real: a dead key silently halves the
    # fallback chain, which shows up only as unexplained AI failures.
    try:
        from src.ai.providers import get_registry

        registry = get_registry()
        print("\nAI providers (live probe):")
        usable = 0
        for name, outcome in sorted(registry.probe_providers().items()):
            if outcome == "ok":
                usable += 1
                print(f"  OK       {name}")
            else:
                print(f"  DEAD     {name:14} {outcome}")
        print(f"  -> {usable} provider(s) actually usable")
        if usable < 2:
            print(
                "  WARNING: fewer than 2 usable AI providers. Groq's free tier "
                "rate-limits hard, so a single working provider means most "
                "articles will be skipped for 'AI failed'. Free keys for the "
                "dead providers above would restore redundancy."
            )
        if usable == 0:
            ok = False
    except Exception as exc:
        print(f"AI probe failed: {exc}")

    return 0 if ok else 1


def _screener_allowlist() -> set | None:
    """Tickers a live screener currently flags as active.

    Used by `scan` mode. Returns ``None`` when the screener is unavailable, in
    which case `scan` degrades to behaving like `run` rather than failing.
    """
    try:
        from src.screening.screener import scan_for_active_smallcaps, scan_price_volume_spikes
        from src.universe.builder import get_universe

        tickers = set()
        try:
            for candidate in scan_price_volume_spikes(list(get_universe().keys()), max_results=15):
                tickers.add(candidate.ticker)
        except Exception as exc:
            logger.warning("Spike scan unavailable: %s", exc)
        try:
            for candidate in scan_for_active_smallcaps(max_results=20):
                tickers.add(candidate.ticker)
        except Exception as exc:
            logger.warning("Small-cap scan unavailable: %s", exc)
        return tickers or None
    except Exception as exc:
        logger.warning("Screener unavailable, continuing without a filter: %s", exc)
        return None


async def cmd_run(args) -> int:
    from src.pipeline.runner import run

    report = await run(
        dry_run=args.dry_run,
        max_signals=args.signals,
        freshness_hours=args.freshness_hours,
        use_cache=args.use_cache,
    )
    return 1 if report.get("errors") else 0


async def cmd_scan(args) -> int:
    """Screener-first: only consider stocks the market is currently flagging."""
    from src.pipeline import runner

    allowlist = _screener_allowlist()
    if allowlist:
        logger.info("Screener flagged %d ticker(s)", len(allowlist))
        print(f"   Screener flagged {len(allowlist)} ticker(s)")
    else:
        print("   Screener unavailable - proceeding without a ticker filter")

    runner.TICKER_ALLOWLIST = allowlist
    report = await runner.run(
        dry_run=args.dry_run,
        max_signals=args.signals,
        freshness_hours=args.freshness_hours,
        use_cache=args.use_cache,
    )
    return 1 if report.get("errors") else 0


def cmd_backtest(args) -> int:
    sys.path.insert(0, str(ROOT / "scripts"))
    from scripts.backtest import resolve_outcomes, show_results

    print("Step 1: resolving signal outcomes from market history...")
    resolve_outcomes(days=30)
    print("Step 2: computing metrics...")
    results = show_results()
    if not results:
        print("No resolved outcomes yet.")
    return 0


def cmd_db(args) -> int:
    from src.store import get_store

    store = get_store()
    print("PERSISTENT STATE")
    for key, value in store.counts().items():
        print(f"   {key:14}: {value}")
    signals = store.recent_signals(days=30, limit=10)
    if signals:
        print("\nRECENT SIGNALS")
        for s in signals:
            print(f"   {s.generated_at[:19]}  {s.ticker:14} "
                  f"price={s.market_price:<10} sent={s.sent}  {s.article_title[:44]}")
    return 0


def cmd_holds(args) -> int:
    from src.storage.db import get_db

    db = get_db()
    print("MANUAL HOLDS (local database - not the persistent store)")
    holdings = db.get_holdings("HOLDING")
    if not holdings:
        print("   none")
    for h in holdings:
        print(f"   {h['name']} ({h['ticker']}) @ Rs{h['entry_price']:,.2f} x{h['quantity']}")
    return 0


def cmd_calibrate(args) -> int:
    from src.analysis.calibration import get_calibrator

    calibrator = get_calibrator()
    calibrator.calibrate_from_db()
    print(calibrator.get_calibration_report())
    return 0


def cmd_config(args) -> int:
    import json

    from src.config import load_settings

    print(json.dumps(load_settings(), indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AlphaScout - Indian market news to validated trade signals",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["run", "scan", "state", "health", "backtest", "db",
                 "holds", "calibrate", "config"],
    )
    parser.add_argument("--signals", type=int, default=MAX_SIGNALS_PER_RUN,
                        help=f"max signals to send (hard cap {MAX_SIGNALS_PER_RUN})")
    parser.add_argument("--freshness-hours", type=int, default=30,
                        help="reject articles published longer ago than this")
    parser.add_argument("--dry-run", action="store_true",
                        help="run everything except the Telegram send")
    parser.add_argument("--use-cache", action="store_true",
                        help="reuse cached articles instead of scraping fresh")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # The cap is enforced in the pipeline too; clamping here keeps the CLI honest.
    args.signals = max(1, min(args.signals, MAX_SIGNALS_PER_RUN))

    if args.command == "state":
        return cmd_state()
    if args.command == "health":
        return cmd_health()
    if args.command == "backtest":
        return cmd_backtest(args)
    if args.command == "db":
        return cmd_db(args)
    if args.command == "holds":
        return cmd_holds(args)
    if args.command == "calibrate":
        return cmd_calibrate(args)
    if args.command == "config":
        return cmd_config(args)

    print_banner(args.command + (" --dry-run" if args.dry_run else ""))
    if args.command == "run":
        return asyncio.run(cmd_run(args))
    if args.command == "scan":
        return asyncio.run(cmd_scan(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
