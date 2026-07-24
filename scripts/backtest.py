#!/usr/bin/env python3
"""
Backtest Script
Replays pipeline on historical news + prices to measure accuracy
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from src.scraping.scraper import scrape_all_sources
from src.analysis.pipeline import analyze_articles
from src.portfolio.manager import PortfolioManager
from src.config import validate_api_keys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


async def run_backtest(days: int = 30, start_date: str = None):
    """Run backtest on historical period"""
    print(f"\n📈 BACKTEST: Last {days} days")
    print("=" * 60)

    # Check if we have cached articles
    articles_file = DATA_DIR / "articles_cache.json"
    if not articles_file.exists():
        print("❌ No cached articles found. Run pipeline first to collect data.")
        return

    with open(articles_file) as f:
        data = json.load(f)

    articles_data = data.get("articles", [])
    print(f"📰 Loaded {len(articles_data)} cached articles")

    # Filter by date if needed
    if start_date:
        start = datetime.fromisoformat(start_date)
        articles_data = [a for a in articles_data
                         if datetime.fromisoformat(a.get("fetched_at", "")) >= start]

    # Run analysis
    print(f"🧠 Analyzing {len(articles_data)} articles...")
    signals = analyze_articles(articles_data, max_signals=10)
    print(f"🎯 Generated {len(signals)} signals")

    # Simulate trades
    portfolio = PortfolioManager(capital=100000)
    results = []

    for signal in signals:
        trade = signal["trade"]
        ticker = signal["prediction"]["ticker"]

        # Get historical price at signal time
        # This would need historical price data - for now use entry price
        entry = trade.get("entry_price_range", "").replace("₹", "").split("-")[0].strip()
        try:
            entry_price = float(entry)
        except:
            entry_price = 0

        if entry_price == 0:
            continue

        # Simulate
        result = {
            "ticker": ticker,
            "date": signal["timestamp"][:10],
            "entry": entry_price,
            "target": entry_price * (1 + trade.get("target_pct", 0) / 100),
            "stop": entry_price * (1 - trade.get("stop_loss_pct", 0) / 100),
            "expected_move": signal["prediction"]["expected_move_pct"],
            "confidence": trade.get("confidence", 0),
            "r_r": trade.get("risk_reward_ratio", 0),
        }

        # Try to get actual outcome from yfinance
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            hist = t.history(period="1mo")
            if not hist.empty:
                # Check price over next 7 days
                entry_idx = hist.index.searchsorted(signal["timestamp"][:10])
                if entry_idx < len(hist) - 7:
                    future = hist.iloc[entry_idx:entry_idx+7]
                    high = future["High"].max()
                    low = future["Low"].min()

                    if high >= result["target"]:
                        result["outcome"] = "WIN"
                        result["actual_pct"] = (high - entry_price) / entry_price * 100
                    elif low <= result["stop"]:
                        result["outcome"] = "LOSS"
                        result["actual_pct"] = (low - entry_price) / entry_price * 100
                    else:
                        result["outcome"] = "OPEN"
                        result["actual_pct"] = (future["Close"].iloc[-1] - entry_price) / entry_price * 100
        except Exception as e:
            result["outcome"] = "ERROR"
            result["actual_pct"] = 0

        results.append(result)

    # Summary
    wins = [r for r in results if r.get("outcome") == "WIN"]
    losses = [r for r in results if r.get("outcome") == "LOSS"]
    open_trades = [r for r in results if r.get("outcome") == "OPEN"]

    print(f"\n📊 RESULTS:")
    print(f"   Total Signals: {len(results)}")
    print(f"   Wins: {len(wins)}")
    print(f"   Losses: {len(losses)}")
    print(f"   Open: {len(open_trades)}")
    if results:
        win_rate = len(wins) / len(results) * 100
        print(f"   Win Rate: {win_rate:.1f}%")
        avg_win = sum(r["actual_pct"] for r in wins) / len(wins) if wins else 0
        avg_loss = sum(r["actual_pct"] for r in losses) / len(losses) if losses else 0
        print(f"   Avg Win: {avg_win:.1f}%")
        print(f"   Avg Loss: {avg_loss:.1f}%")

    # Save detailed results
    out_file = DATA_DIR / f"backtest_{datetime.now().strftime('%Y%m%d')}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n💾 Saved to {out_file}")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    args = parser.parse_args()

    asyncio.run(run_backtest(args.days, args.start))


if __name__ == "__main__":
    import asyncio
    main()