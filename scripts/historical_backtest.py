#!/usr/bin/env python3
"""
AlphaScout Historical Price Backtest
Simulates the mechanical spike-trigger strategy across the universe on
N years of daily yfinance data to estimate signal accuracy.

The trigger mirrors screener.scan_price_volume_spikes:
  - price spike:  |day_change%| >= price_threshold
  - volume spike: today_volume / 20d_avg_volume >= volume_threshold
  Trigger fires when EITHER condition is met (same as the live scanner).

Execution model (conservative):
  - Entry: next trading day OPEN after the signal day
  - Exit: stop hit (intraday low <= stop) takes priority over target hit on the
    same day; otherwise target hit (intraday high >= target); else exit at the
    close of the last allowed day (HOLD).
  - Cooldown: no overlapping positions on the same ticker.

Metrics computed per parameter config: win rate, avg win/loss %, profit factor,
expectancy, avg R-multiple, max drawdown, plus breakdowns by sector, spike type,
market-cap bucket, and year. All results saved to data/historical_backtest.json.
"""
import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.universe.builder import get_universe  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = ROOT / "data"
PRICE_DIR = DATA_DIR / "price_history"


# ─────────────────────────────────────────────────────────────────────────────
# Parameter matrix — "backtest a lot": many trigger/exit/horizon combinations
# ─────────────────────────────────────────────────────────────────────────────
CONFIGS = [
    {"name": "default",             "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5},
    {"name": "strong_price",        "price_th": 5.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5},
    {"name": "volume_confirmed",    "price_th": 3.0, "vol_th": 3.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5},
    {"name": "strict",              "price_th": 5.0, "vol_th": 3.0, "target": 12, "stop": 5, "hold": 7, "cooldown": 7},
    {"name": "tight_rr",            "price_th": 3.0, "vol_th": 2.0, "target": 8,  "stop": 5, "hold": 7, "cooldown": 5},
    {"name": "wider_rr",            "price_th": 3.0, "vol_th": 2.0, "target": 15, "stop": 7, "hold": 7, "cooldown": 5},
    {"name": "fast_horizon",        "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 3, "cooldown": 3},
    {"name": "loose",               "price_th": 2.0, "vol_th": 1.5, "target": 10, "stop": 5, "hold": 7, "cooldown": 4},
    {"name": "wide_loose",          "price_th": 2.0, "vol_th": 1.5, "target": 12, "stop": 6, "hold": 10, "cooldown": 6},
    {"name": "long_only_momentum",  "price_th": 4.0, "vol_th": 2.0, "target": 12, "stop": 6, "hold": 10, "cooldown": 7},
    # ── Refined variants isolating sub-edges seen in the full-sample breakdown ──
    {"name": "price_only",       "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5,
     "filters": {"spike_types": ["price", "both"]}},
    {"name": "small_caps",       "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5,
     "filters": {"cap_max_cr": 5000}},
    {"name": "price_only_small", "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5,
     "filters": {"spike_types": ["price", "both"], "cap_max_cr": 5000}},
    {"name": "defence_railways", "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5,
     "filters": {"sectors": ["defence", "railways", "manufacturing_pli"]}},
    {"name": "small_defence_rail", "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5,
     "filters": {"spike_types": ["price", "both"], "cap_max_cr": 2000,
                 "sectors": ["defence", "railways", "manufacturing_pli"]}},
    {"name": "default_optimistic", "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5,
     "exit_priority": "target"},
    {"name": "price_only_optimistic", "price_th": 3.0, "vol_th": 2.0, "target": 10, "stop": 5, "hold": 7, "cooldown": 5,
     "exit_priority": "target", "filters": {"spike_types": ["price", "both"]}},
]


# ─────────────────────────────────────────────────────────────────────────────
# Data download + caching
# ─────────────────────────────────────────────────────────────────────────────
def load_price_data(ticker: str, years: int, force_refresh: bool) -> Optional[pd.DataFrame]:
    """Download or load cached daily OHLCV for a ticker."""
    cache_file = PRICE_DIR / f"{ticker.replace('.', '_')}_{years}y.csv"
    if cache_file.exists() and not force_refresh:
        try:
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            if len(df) > 60:
                return df
        except Exception:
            pass

    try:
        t = yf.Ticker(ticker)
        df = t.history(period=f"{years}y", auto_adjust=True)
    except Exception as e:
        logger.debug(f"Download failed {ticker}: {e}")
        return None

    if df is None or df.empty:
        logger.debug(f"No data for {ticker}")
        return None

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    if len(df) < 60:
        logger.debug(f"Too little data for {ticker}: {len(df)} rows")
        return None

    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(cache_file)
    except Exception:
        pass
    time.sleep(0.3)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Per-ticker trade simulation
# ─────────────────────────────────────────────────────────────────────────────
def simulate_ticker(
    ticker: str,
    sector: str,
    market_cap_cr: float,
    df: pd.DataFrame,
    cfg: Dict,
) -> List[Dict]:
    """Walk the price series and simulate spike-triggered trades."""
    df = df.copy()
    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    open_ = df["Open"].astype(float)
    vol = df["Volume"].astype(float)

    prev_close = close.shift(1)
    day_change_pct = (close / prev_close - 1.0) * 100.0
    avg_vol_20d = vol.rolling(20).mean().shift(1)  # prior 20 days only (no lookahead)
    vol_ratio = vol / avg_vol_20d

    price_th = cfg["price_th"]
    vol_th = cfg["vol_th"]
    target_pct = cfg["target"]
    stop_pct = cfg["stop"]
    hold = cfg["hold"]
    cooldown = cfg["cooldown"]
    # Same-day ambiguity: which order to assume High>=target and Low<=stop both hit.
    # Conservative default = stop first; optimistic = target first.
    exit_priority = cfg.get("exit_priority", "stop")

    n = len(df)
    trades: List[Dict] = []
    next_allowed = 0  # index: earliest signal day allowed (cooldown since last entry)

    for i in range(1, n):
        if i < next_allowed:
            continue
        chg = day_change_pct.iloc[i]
        vratio = vol_ratio.iloc[i]
        if pd.isna(chg) or pd.isna(vratio):
            continue

        is_price_spike = abs(chg) >= price_th
        is_vol_spike = vratio >= vol_th
        if not (is_price_spike or is_vol_spike):
            continue

        # Entry at next day open
        if i + 1 >= n:
            continue
        entry = float(open_.iloc[i + 1])
        if pd.isna(entry) or entry <= 0:
            continue

        target_price = entry * (1 + target_pct / 100.0)
        stop_price = entry * (1 - stop_pct / 100.0)
        risk = entry - stop_price

        # Walk forward up to `hold` trading days
        exit_price = None
        outcome = None
        for j in range(i + 1, min(i + 1 + hold, n)):
            hit_stop = low.iloc[j] <= stop_price
            hit_target = high.iloc[j] >= target_price
            if hit_stop and hit_target:
                if exit_priority == "target":
                    exit_price, outcome = target_price, "WIN"
                    break
                exit_price, outcome = stop_price, "LOSS"
                break
            if hit_stop:
                exit_price, outcome = stop_price, "LOSS"
                break
            if hit_target:
                exit_price, outcome = target_price, "WIN"
                break
            exit_price = float(close.iloc[j])
            outcome = "HOLD"

        if exit_price is None:
            continue

        pnl_pct = (exit_price - entry) / entry * 100.0
        r_multiple = pnl_pct / (risk / entry * 100.0) if risk > 0 else 0.0

        spike_type = "both"
        if is_price_spike and not is_vol_spike:
            spike_type = "price"
        elif is_vol_spike and not is_price_spike:
            spike_type = "volume"

        trades.append({
            "ticker": ticker,
            "sector": sector,
            "market_cap_cr": market_cap_cr,
            "signal_date": df.index[i].strftime("%Y-%m-%d"),
            "entry_date": df.index[i + 1].strftime("%Y-%m-%d"),
            "signal_change_pct": round(float(chg), 2),
            "signal_vol_ratio": round(float(vratio), 2),
            "spike_type": spike_type,
            "entry": round(entry, 2),
            "exit": round(exit_price, 2),
            "target": round(target_price, 2),
            "stop": round(stop_price, 2),
            "pnl_pct": round(pnl_pct, 2),
            "r_multiple": round(r_multiple, 2),
            "outcome": outcome,
        })

        # Cooldown: don't open another position on this ticker for `cooldown` bars
        next_allowed = i + cooldown

    # Apply optional filters (refined sub-strategies)
    filters = cfg.get("filters")
    if filters:
        if filters.get("spike_types"):
            trades = [t for t in trades if t["spike_type"] in filters["spike_types"]]
        if filters.get("cap_max_cr") is not None:
            trades = [t for t in trades if t["market_cap_cr"] <= filters["cap_max_cr"]]
        if filters.get("sectors"):
            trades = [t for t in trades if t["sector"] in filters["sectors"]]

    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────
def _summary(trades: List[Dict]) -> Dict:
    """Lightweight aggregation for breakdown groups (no nested recursion)."""
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "avg_r": 0.0, "profit_factor": 0.0, "expectancy_pct": 0.0}
    wins = [t for t in trades if t["outcome"] == "WIN"]
    losses = [t for t in trades if t["outcome"] == "LOSS"]
    gross_profit = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_r": round(sum(t["r_multiple"] for t in trades) / len(trades), 2),
        "profit_factor": round(pf, 2),
        "expectancy_pct": round(sum(t["pnl_pct"] for t in trades) / len(trades), 2),
    }


def compute_metrics(trades: List[Dict]) -> Dict:
    if not trades:
        return {"trades": 0}

    wins = [t for t in trades if t["outcome"] == "WIN"]
    losses = [t for t in trades if t["outcome"] == "LOSS"]
    holds = [t for t in trades if t["outcome"] == "HOLD"]

    total = len(trades)
    win_rate = len(wins) / total * 100
    closed = wins + losses
    closed_rate = len(wins) / len(closed) * 100 if closed else 0.0

    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0.0

    gross_profit = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    avg_r = sum(t["r_multiple"] for t in trades) / total
    expectancy = sum(t["r_multiple"] for t in trades) / total

    # Equity curve in R-units (equal risk per trade), max drawdown
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for t in trades:
        equity += t["r_multiple"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    # By-sector / by-spike-type / by-cap-bucket / by-year
    def bucket(rows, key):
        out = {}
        for t in rows:
            out.setdefault(t[key], []).append(t)
        return {k: _summary(grp) for k, grp in out.items()}

    def cap_bucket(cap):
        if cap < 500:
            return "<500Cr"
        if cap < 2000:
            return "500-2000Cr"
        if cap < 5000:
            return "2000-5000Cr"
        if cap < 20000:
            return "5000-20000Cr"
        return ">20000Cr"

    years = {}
    for t in trades:
        years.setdefault(t["entry_date"][:4], []).append(t)
    by_year = {y: _summary(grp) for y, grp in sorted(years.items())}

    return {
        "trades": total,
        "wins": len(wins),
        "losses": len(losses),
        "holds": len(holds),
        "win_rate": round(win_rate, 1),
        "closed_win_rate": round(closed_rate, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_r_multiple": round(avg_r, 2),
        "expectancy_r": round(expectancy, 2),
        "expectancy_pct": round(sum(t["pnl_pct"] for t in trades) / total, 2),
        "max_drawdown_r": round(max_dd, 2),
        "by_sector": bucket(trades, "sector"),
        "by_spike_type": bucket(trades, "spike_type"),
        "by_cap_bucket": bucket([{**t, "cap_bucket": cap_bucket(t["market_cap_cr"])} for t in trades], "cap_bucket"),
        "by_year": by_year,
    }


def run_config(ticker_dfs: Dict[str, Dict], cfg: Dict) -> Dict:
    trades = []
    for ticker, info in ticker_dfs.items():
        trades.extend(simulate_ticker(ticker, info["sector"], info["market_cap_cr"], info["df"], cfg))
    metrics = compute_metrics(trades)
    metrics["config"] = cfg["name"]
    metrics["signals_total"] = len(trades)
    return metrics


# ─────────────────────────────────────────────────────────────────────────────
# Report printing
# ─────────────────────────────────────────────────────────────────────────────
def print_report(results: List[Dict], cfg_names: Dict[str, str]):
    print("\n" + "=" * 92)
    print("  ALPHASCOUT HISTORICAL PRICE BACKTEST — SPIKE-TRIGGER STRATEGY")
    print("=" * 92)
    print(f"  Configs run: {len(results)} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("-" * 92)
    hdr = (f"  {'config':<22} {'tr':>5} {'win%':>6} {'win%*':>6} {'avgR':>6} "
           f"{'PF':>6} {'expR':>6} {'avgWin':>7} {'avgLoss':>7} {'maxDD':>6}")
    print(hdr)
    print("-" * 92)
    for r in results:
        cfg_desc = cfg_names.get(r["config"], "")
        print(f"  {r['config']:<22} {r['trades']:>5} {r['win_rate']:>6.1f} "
              f"{r['closed_win_rate']:>6.1f} {r['avg_r_multiple']:>6.2f} "
              f"{r['profit_factor']:>6.2f} {r['expectancy_r']:>6.2f} "
              f"{r['avg_win_pct']:>7.2f} {r['avg_loss_pct']:>7.2f} {r['max_drawdown_r']:>6.2f}")
        if cfg_desc:
            print(f"      -> {cfg_desc}")
    print("-" * 92)

    # Best overall + breakdowns for the default config
    default = next((r for r in results if r["config"] == "default"), results[0])
    print(f"\n  DETAILED BREAKDOWN — '{default['config']}' ({default['trades']} trades):")
    for label, key in [("Sector", "by_sector"), ("Spike type", "by_spike_type"), ("Cap bucket", "by_cap_bucket")]:
        print(f"\n   {label}:")
        print(f"   {'group':<22} {'trades':>6} {'win%':>7} {'avgR':>7} {'PF':>6} {'exp%':>7}")
        for grp, m in sorted(default[key].items(), key=lambda kv: -kv[1]["trades"]):
            print(f"   {grp:<22} {m['trades']:>6} {m['win_rate']:>7.1f} {m['avg_r']:>7.2f} "
                  f"{m['profit_factor']:>6.2f} {m['expectancy_pct']:>7.2f}")

    print("\n   By year:")
    for y, m in default["by_year"].items():
        print(f"   {y:<22} {m['trades']:>6} {m['win_rate']:>7.1f} {m['avg_r']:>7.2f} "
              f"{m['profit_factor']:>6.2f} {m['expectancy_pct']:>7.2f}")

    # Cross-config summary
    valid = [r for r in results if r["trades"] > 0]
    if valid:
        wr = sorted(r["closed_win_rate"] for r in valid)
        exp = sorted(r["expectancy_r"] for r in valid)
        print("\n" + "-" * 92)
        print("  CROSS-CONFIG SUMMARY:")
        print(f"   Closed-win-rate range: {wr[0]:.1f}% – {wr[-1]:.1f}% (median {wr[len(wr)//2]:.1f}%)")
        print(f"   Expectancy-R range:    {exp[0]:.2f}R – {exp[-1]:.2f}R (median {exp[len(exp)//2]:.2f}R)")
        pos_exp = sum(1 for r in valid if r["expectancy_r"] > 0)
        print(f"   Configs with +EV:      {pos_exp}/{len(valid)}")
    print("=" * 92)


def main():
    parser = argparse.ArgumentParser(description="AlphaScout Historical Price Backtest")
    parser.add_argument("--years", type=int, default=2, help="Years of history per ticker")
    parser.add_argument("--start", help="Optional start date YYYY-MM-DD")
    parser.add_argument("--end", help="Optional end date YYYY-MM-DD")
    parser.add_argument("--refresh-data", action="store_true", help="Force re-download price data")
    parser.add_argument("--configs", help="Comma-separated config names to run (default: all)")
    parser.add_argument("--out", default=str(DATA_DIR / "historical_backtest.json"))
    args = parser.parse_args()

    universe = get_universe()
    print(f"\nUniverse: {len(universe)} stocks")

    names = {c["name"]: c for c in CONFIGS}
    if args.configs:
        chosen = [names[c.strip()] for c in args.configs.split(",") if c.strip() in names]
    else:
        chosen = CONFIGS

    # Download price data
    ticker_dfs: Dict[str, Dict] = {}
    print(f"Downloading {args.years} years of price data (cached in {PRICE_DIR})...")
    for ticker, stock in universe.items():
        df = load_price_data(ticker, args.years, args.refresh_data)
        if df is not None:
            if args.start:
                df = df[df.index >= pd.Timestamp(args.start)]
            if args.end:
                df = df[df.index <= pd.Timestamp(args.end)]
            if len(df) >= 60:
                ticker_dfs[ticker] = {
                    "df": df,
                    "sector": stock.sector,
                    "market_cap_cr": stock.market_cap_cr,
                }
        if len(ticker_dfs) % 10 == 0 and len(ticker_dfs) > 0:
            print(f"   ...{len(ticker_dfs)} tickers with data")

    print(f"\nDownloaded valid history for {len(ticker_dfs)}/{len(universe)} universe stocks")

    results = []
    cfg_desc = {c["name"]: (f"price>={c['price_th']}% | vol>={c['vol_th']}x | target+{c['target']}% | "
                            f"stop-{c['stop']}% | hold {c['hold']}d | cooldown {c['cooldown']}d"
                            + (f" | filters={c.get('filters')}" if c.get("filters") else "")) for c in CONFIGS}
    for cfg in chosen:
        r = run_config(ticker_dfs, cfg)
        results.append(r)
        print(f"  Ran '{cfg['name']}': {r['trades']} trades, win rate {r['win_rate']}%, expectancy {r['expectancy_r']}R")

    print_report(results, cfg_desc)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "universe_size": len(universe),
        "universe_with_data": len(ticker_dfs),
        "years": args.years,
        "results": results,
        "universe_tickers": sorted(universe.keys()),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"\nSaved full results to {out_path}")


if __name__ == "__main__":
    main()
