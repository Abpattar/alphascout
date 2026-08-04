#!/usr/bin/env python3
"""
AlphaScout Backtest Harness
Replays pipeline on stored articles, fetches actual outcomes, computes metrics.
Reads from SQLite DB, fetches price data from yfinance.
"""
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import yfinance as yf

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.storage.db import get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = ROOT / "data"


def resolve_outcomes(days: int = 30, batch_size: int = 20, min_age_days: int = 1) -> Dict:
    """Fetch actual price outcomes for unresolved signals from yfinance."""
    from datetime import date
    db = get_db()
    signals = db.get_unresolved_signals(days=days)

    if not signals:
        print("No unresolved signals found.")
        return {"resolved": 0, "skipped": 0, "errors": 0}

    print(f"\nResolving {len(signals)} unresolved signals...")
    resolved = 0
    skipped = 0
    errors = 0

    for i, sig in enumerate(signals):
        ticker = sig["ticker"]
        signal_id = sig["signal_id"]
        entry_price = sig["entry_price"]
        created_at = sig["created_at"]

        if not ticker or not entry_price:
            skipped += 1
            continue

        # Skip brand-new signals: there is no meaningful future price data yet
        # (also avoids a wasted yfinance call for every same-day signal).
        try:
            if (date.today() - datetime.fromisoformat(created_at).date()).days < min_age_days:
                skipped += 1
                continue
        except Exception:
            pass

        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1mo")
            if hist.empty:
                skipped += 1
                continue

            # Find entry date in history
            entry_date = datetime.fromisoformat(created_at).date()
            hist.index = hist.index.tz_localize(None)
            entry_idx = None
            for idx, dt in enumerate(hist.index):
                if dt.date() >= entry_date:
                    entry_idx = idx
                    break

            if entry_idx is None:
                skipped += 1
                continue

            # Extract price points
            remaining = hist.iloc[entry_idx:]
            outcome = {
                "signal_id": signal_id,
                "ticker": ticker,
                "entry_price": entry_price,
            }

            # Price at +1, +3, +5, +7 days
            for label, offset in [("price_at_1d", 1), ("price_at_3d", 3),
                                  ("price_at_5d", 5), ("price_at_7d", 7)]:
                if len(remaining) > offset:
                    outcome[label] = round(float(remaining.iloc[offset]["Close"]), 2)
                else:
                    outcome[label] = None

            # High/low over 7 days
            window = remaining.iloc[:min(8, len(remaining))]
            outcome["high_7d"] = round(float(window["High"].max()), 2)
            outcome["low_7d"] = round(float(window["Low"].min()), 2)

            # Determine outcome
            target_price = sig.get("target_price", 0)
            stop_loss = sig.get("stop_loss_price", 0)
            target_pct = sig.get("target_pct", 0)
            stop_pct = sig.get("stop_loss_pct", 0)

            if not target_price and entry_price and target_pct:
                target_price = entry_price * (1 + target_pct / 100)
            if not stop_loss and entry_price and stop_pct:
                stop_loss = entry_price * (1 - stop_pct / 100)

            target_hit = 0
            stop_hit = 0
            outcome_str = "OPEN"
            actual_pnl_pct = 0

            if outcome["high_7d"] and target_price and outcome["high_7d"] >= target_price:
                target_hit = 1
                outcome_str = "WIN"
                actual_pnl_pct = (target_price - entry_price) / entry_price * 100
            elif outcome["low_7d"] and stop_loss and outcome["low_7d"] <= stop_loss:
                stop_hit = 1
                outcome_str = "LOSS"
                actual_pnl_pct = (stop_loss - entry_price) / entry_price * 100
            elif outcome.get("price_at_7d"):
                outcome_str = "HOLD"
                actual_pnl_pct = (outcome["price_at_7d"] - entry_price) / entry_price * 100
            elif window is not None and len(window) > 0:
                last_close = float(window.iloc[-1]["Close"])
                actual_pnl_pct = (last_close - entry_price) / entry_price * 100
                if actual_pnl_pct > 0:
                    outcome_str = "HOLD"
                else:
                    outcome_str = "HOLD"

            # Calculate R-multiple
            risk = entry_price - stop_loss if stop_loss and stop_loss < entry_price else entry_price * 0.05
            reward = target_price - entry_price if target_price and target_price > entry_price else entry_price * 0.10
            if risk > 0:
                r_multiple = round(actual_pnl_pct / (risk / entry_price * 100), 2) if risk else 0
            else:
                r_multiple = 0

            outcome.update({
                "target_hit": target_hit,
                "stop_hit": stop_hit,
                "actual_r_multiple": r_multiple,
                "actual_pnl_pct": round(actual_pnl_pct, 2),
                "outcome": outcome_str,
                "resolved_at": datetime.now().isoformat(),
            })

            db.store_outcome(outcome)
            resolved += 1

            if (i + 1) % 10 == 0:
                print(f"  Progress: {i + 1}/{len(signals)} resolved={resolved} errors={errors}")

            time.sleep(0.3)  # Rate limit yfinance

        except Exception as e:
            errors += 1
            logger.debug(f"Failed for {ticker}: {e}")

    print(f"\nResolution complete: {resolved} resolved, {skipped} skipped, {errors} errors")
    return {"resolved": resolved, "skipped": skipped, "errors": errors}


def run_backtest_replay(days: int = 30, max_articles: int = 50, max_signals: int = 10) -> List[Dict]:
    """Replay stored articles through the pipeline and generate new signals."""
    from src.scraping.scraper import scrape_all_sources
    from src.analysis.pipeline import analyze_articles

    db = get_db()
    articles = db.get_recent_articles(hours=days * 24, limit=max_articles)
    print(f"\nReplaying {len(articles)} stored articles through pipeline...")

    # Convert DB articles back to dict format for pipeline
    article_dicts = []
    for a in articles:
        article_dicts.append({
            "title": a["title"],
            "url": a["url"],
            "source": a["source"],
            "category": a["category"],
            "content": a["content"],
            "summary": a["summary"],
            "published": a["published_at"],
            "fetched_at": a["scraped_at"],
        })

    signals = analyze_articles(article_dicts, max_signals=max_signals)
    print(f"Generated {len(signals)} signals from replay")

    return signals


def show_results() -> Dict:
    """Display backtest results from stored outcomes."""
    db = get_db()
    outcomes = db.get_all_outcomes(limit=1000)
    raw_total = len(db.get_all_outcomes(limit=1000, dedupe=False))

    if not outcomes:
        print("\nNo outcomes stored yet. Run 'resolve' first to fetch price data.")
        return {}

    if raw_total != len(outcomes):
        print(f"\nℹ️  Collapsed {raw_total - len(outcomes)} same-ticker/same-day duplicates "
              f"({raw_total} raw → {len(outcomes)} independent signals)")

    # Compute metrics
    total = len(outcomes)
    wins = [o for o in outcomes if o["outcome"] == "WIN"]
    losses = [o for o in outcomes if o["outcome"] == "LOSS"]
    holds = [o for o in outcomes if o["outcome"] == "HOLD"]
    open_trades = [o for o in outcomes if o["outcome"] == "OPEN"]

    win_rate = len(wins) / total * 100 if total else 0
    avg_win_pct = sum(o["actual_pnl_pct"] for o in wins) / len(wins) if wins else 0
    avg_loss_pct = sum(o["actual_pnl_pct"] for o in losses) / len(losses) if losses else 0
    avg_r = sum(o["actual_r_multiple"] for o in outcomes if o["actual_r_multiple"]) / max(1, len([o for o in outcomes if o["actual_r_multiple"]]))

    # Profit factor
    gross_profit = sum(o["actual_pnl_pct"] for o in wins) if wins else 0
    gross_loss = abs(sum(o["actual_pnl_pct"] for o in losses)) if losses else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Max drawdown (running)
    cumulative = 0
    peak = 0
    max_dd = 0
    for o in sorted(outcomes, key=lambda x: x.get("resolved_at", "")):
        cumulative += o["actual_pnl_pct"]
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

    # Expectancy
    expectancy = (win_rate / 100 * avg_win_pct) + ((1 - win_rate / 100) * avg_loss_pct) if total else 0

    # By confidence bucket
    conf_buckets = {}
    for o in outcomes:
        sig = db.get_signal(o["signal_id"]) if o.get("signal_id") else None
        if sig:
            conf = sig.get("confidence", 0)
            bucket = f"{(conf // 10) * 10}-{(conf // 10) * 10 + 9}"
            if bucket not in conf_buckets:
                conf_buckets[bucket] = {"total": 0, "wins": 0, "losses": 0}
            conf_buckets[bucket]["total"] += 1
            if o["outcome"] == "WIN":
                conf_buckets[bucket]["wins"] += 1
            elif o["outcome"] == "LOSS":
                conf_buckets[bucket]["losses"] += 1

    print("\n" + "=" * 70)
    print("  ALPHASCOUT BACKTEST RESULTS")
    print("=" * 70)
    print(f"  Total Signals:     {total}")
    print(f"  Wins:              {len(wins)}")
    print(f"  Losses:            {len(losses)}")
    print(f"  Holds:             {len(holds)}")
    print(f"  Open/Unresolved:   {len(open_trades)}")
    print(f"  ---")
    print(f"  Win Rate:          {win_rate:.1f}%")
    print(f"  Avg Win:           {avg_win_pct:+.2f}%")
    print(f"  Avg Loss:          {avg_loss_pct:+.2f}%")
    print(f"  Avg R-Multiple:    {avg_r:+.2f}R")
    print(f"  Profit Factor:     {profit_factor:.2f}")
    print(f"  Expectancy:        {expectancy:+.2f}% per trade")
    print(f"  Max Drawdown:      {max_dd:.2f}%")
    print("=" * 70)

    if conf_buckets:
        print("\n  CONFIDENCE CALIBRATION:")
        print(f"  {'Bucket':>12}  {'Total':>6}  {'Wins':>5}  {'Losses':>6}  {'Win Rate':>9}")
        for bucket in sorted(conf_buckets.keys()):
            b = conf_buckets[bucket]
            wr = b["wins"] / b["total"] * 100 if b["total"] else 0
            print(f"  {bucket:>12}  {b['total']:>6}  {b['wins']:>5}  {b['losses']:>6}  {wr:>8.1f}%")

    # Save results
    results = {
        "total": total,
        "wins": len(wins),
        "losses": len(losses),
        "holds": len(holds),
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win_pct, 2),
        "avg_loss_pct": round(avg_loss_pct, 2),
        "avg_r_multiple": round(avg_r, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "max_drawdown": round(max_dd, 2),
        "confidence_calibration": conf_buckets,
        "generated_at": datetime.now().isoformat(),
    }

    out_file = DATA_DIR / f"backtest_results_{datetime.now().strftime('%Y%m%d')}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved to {out_file}")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AlphaScout Backtest Harness")
    parser.add_argument("action", nargs="?", default="resolve",
                        choices=["resolve", "replay", "results"],
                        help="resolve=fetch outcomes, replay=re-run pipeline, results=show metrics")
    parser.add_argument("--days", type=int, default=30,
                        help="Lookback period in days")
    parser.add_argument("--max-articles", type=int, default=50,
                        help="Max articles for replay")
    parser.add_argument("--max-signals", type=int, default=10,
                        help="Max signals for replay")
    args = parser.parse_args()

    if args.action == "resolve":
        resolve_outcomes(days=args.days)
    elif args.action == "replay":
        run_backtest_replay(days=args.days, max_articles=args.max_articles, max_signals=args.max_signals)
    elif args.action == "results":
        show_results()


if __name__ == "__main__":
    main()
