# AlphaScout Session Memory
**Last Updated:** 2026-07-26 (Session 7)
**Project Root:** `D:\Codes\alphascout`

---

## Project Objective
Build "AlphaScout" — a multi-sector small-cap news→trade signal bot that:
- Scrapes Indian news sources for market-moving catalysts
- Analyzes articles via AI ensemble (6 providers)
- Generates buy/sell signals for stocks
- 3-7 day holding period, min 10% upside, R:R minimum 2:1
- Sends signals to Telegram

---

## GitHub Repository
- **URL**: https://github.com/Abpattar/alphascout
- **Visibility**: Public
- **Branch**: master
- **Initial commit**: 24 files, 6480 insertions
- **GitHub User**: Abpattar

### Git Setup
- `gh` CLI: `~/.local/bin/gh`
- Token stored: `~/.config/gh/hosts.yml`
- Credential helper: `!gh auth git-credential`
- `.gitignore` excludes: `venv/`, `.env`, `data/*.json`, `__pycache__/`, `*.enc`, `credentials.*`

### GitHub Actions (for future)
- Token has `repo` scope — can create repos and push
- Missing `read:org` scope (harmless, only for org features)

---

## Current Status: PRODUCTION-QUALITY PIPELINE + PERSISTENT STORAGE

### What Works ✅
- **Pipeline**: End-to-end (scrape → analyze → signal)
- **Telegram**: Connected, signals delivered (`@AlphaScoutSignals_bot`)
- **AI Providers**: 6 working (Groq x8, Cerebras, OpenRouter, Gemini, NVIDIA NIM)
- **Ticker extraction**: Fixed false positive matching
- **Provider loading**: dotenv loaded at import time
- **Universe**: 75 stocks + on-the-fly expansion
- **Scraper**: Config-driven (reads from `config/sources.yaml`, 25 sources)
- **On-the-fly ticker validation**: Unknown tickers validated via yfinance in real-time
- **Known ticker map**: 98 entries mapping AI-generated tickers to correct ones
- **Name-based search**: Fallback when ticker validation fails
- **Large-cap penalty**: Large-caps included but confidence reduced 15%
- **Signal deduplication**: Best signal per ticker only

### Session 5 Changes (Today)
1. ✅ **Added on-the-fly ticker validation** — `validate_ticker_on_the_fly()` in `builder.py` fetches yfinance data for unknown tickers, adds to universe dynamically
2. ✅ **Added known ticker map** — 98 entries mapping AI-generated tickers to correct ones (e.g., HIMADRI→HSCL.NS, RRPDEFENSE→RRPDEFENSE.BO)
3. ✅ **Added name-based search fallback** — `_search_ticker_by_name()` uses yfinance Search API when ticker validation fails
4. ✅ **Fixed NS→BO fallback** — When AI says `.NS` but stock is only on BSE, correctly maps to `.BO`
5. ✅ **Tightened filters** — Hard reject: micro-cap (<₹50Cr), penny stock (<₹30). Soft penalty: large-cap (>₹5000Cr) gets 15% confidence reduction
6. ✅ **Improved error handling** — Pipeline wraps each stage in try/except, logs specific discard reasons
7. ✅ **Better logging** — DISCARDED/Note/REJECTED messages for debugging
8. ✅ **Fixed triage prompt** — Removed "old news" and "general discussion" filters that were too aggressive
9. ✅ **Reduced timeouts** — Provider timeouts: 60s→20s, article analysis: 120s→60s, batch timeout: 60s→90s
10. ✅ **Added `scan` command** — Screener-first approach (NSE gainers → Screener.in → Trendlyne → match to news)

### Session 6 Changes
1. ✅ **Created GitHub repository** — https://github.com/Abpattar/alphascout (public)
2. ✅ **Installed `gh` CLI** — Located at `~/.local/bin/gh`, version 2.67.0
3. ✅ **Configured git credentials** — Token stored in `~/.config/gh/hosts.yml`, credential helper set to `!gh auth git-credential`
4. ✅ **Initial push** — 24 files, 6480 insertions (excluded venv, .env, credentials, cache files)

### Session 7 Changes — Phase 1: Database & Logging Infrastructure
1. ✅ **Created `src/storage/db.py`** — SQLite database with 4 tables: `raw_articles`, `llm_analysis`, `signals`, `outcomes`
2. ✅ **Created `src/storage/__init__.py`** — Package init with `get_db()` singleton
3. ✅ **Wired scraper → DB** — Every scraped article is now stored in `raw_articles` table
4. ✅ **Wired pipeline → DB** — Every LLM analysis stage output stored in `llm_analysis` table, final signals in `signals` table
5. ✅ **Added `db` command to main.py** — `python main.py db` shows database stats (articles, analyses, signals, outcomes, win rate)
6. ✅ **Thread-safe** — Uses WAL mode and threading.local() for concurrent access
7. ✅ **Zero-config** — SQLite file auto-created at `data/alphascout.db`, no server needed

### Session 7 Changes — Phase 2: Backtesting Harness
1. ✅ **Rewrote `scripts/backtest.py`** — Full backtest harness with 3 actions: `resolve`, `replay`, `results`
2. ✅ **`resolve` action** — Fetches actual price outcomes from yfinance for unresolved signals, stores in `outcomes` table
3. ✅ **`replay` action** — Replays stored articles through pipeline to generate new signals
4. ✅ **`results` action** — Computes win rate, avg R-multiple, profit factor, max drawdown, expectancy, and confidence calibration buckets
5. ✅ **Updated `main.py` backtest command** — Now runs resolve + show results automatically

### Session 7 Changes — Phase 3: Confidence Calibration
1. ✅ **Created `src/analysis/calibration.py`** — ConfidenceCalibrator maps raw LLM confidence to calibrated confidence using historical outcomes
2. ✅ **5 confidence buckets** — 60-69, 70-79, 80-89, 90-95, 96-100 — each tracks actual win rate
3. ✅ **Pipeline integration** — `_format_output()` now includes `calibrated_confidence` and `auto_execute` flag
4. ✅ **Added `calibrate` command** — `python main.py calibrate` rebuilds calibration from stored outcomes
5. ✅ **Signal display updated** — Shows both raw and calibrated confidence, with reason for auto-execute decision
6. ✅ **Minimum data threshold** — Auto-execution blocked until >=5 signals in each confidence bucket

### Session 7 Changes — Phase 4: Source Trust Tiers & PR/Pump Filters
1. ✅ **Added `tier` field to all 25 sources** — Tier 1: Govt/exchanges (5), Tier 2: Mainstream/market (14), Tier 3: Niche (6)
2. ✅ **Updated triage prompt** — Now detects promotional language, PR-only sources, suspicious timing, lack of independent corroboration
3. ✅ **Added `pr_pump_risk`, `pr_pump_flags`, `independent_sources_count` to TriageResult** — LLM now flags pump risk
4. ✅ **PR/pump filtering in pipeline** — HIGH risk = reject, MEDIUM risk = 20% confidence penalty
5. ✅ **Source tier wired into scraper** — Articles carry their source tier for downstream use
6. ✅ **Impact analysis prompt updated** — Considers source tier in confidence assessment

### Session 7 Changes — Phase 5: Portfolio Risk Rules
1. ✅ **Fixed `self.mapper` bug** — `_get_sector()` now uses `get_universe()` instead of non-existent `self.mapper`
2. ✅ **Added `PERSONAL_USE_ONLY` flag** — SEBI compliance, loaded from `config/settings.yaml`
3. ✅ **Added `paper_trading` mode** — All trades logged but not executed, mode shown in logs
4. ✅ **Max drawdown kill-switch** — Tracks weekly PnL, pauses auto-execution if weekly loss >= 8%
5. ✅ **Hard position sizing limits** — Max 10% per position, min 1%, max 50% portfolio allocation
6. ✅ **Max single loss check** — Rejects signals with stop loss > 5%
7. ✅ **Min daily traded value** — Configurable threshold (default ₹1 Cr/day)
8. ✅ **Weekly drawdown reset** — Automatically resets on new calendar week

### Session 7 Changes — Phase 6: Universe Construction Rules
1. ✅ **Rule-based filters from config** — All thresholds (price, cap, volume, daily value) in `config/settings.yaml`
2. ✅ **Added daily traded value filter** — Rejects stocks with < ₹1 Cr/day traded value (liquidity check)
3. ✅ **Universe change logging** — Logs rejected stocks with reasons to `data/universe_changes.jsonl` for bias detection
4. ✅ **Configurable logging** — `log_changes: true/false` in settings.yaml

### Production Test Results
```
#1 RRP Defense [RRPDEFENSE.BO] — STRONG_BUY (LONG)
   📰 Rs 64.31 cr defence deal: RRP Defense to manufacture over 16,000 weapon sights
   🎯 Target: +12.0% | Stop: -6.5% | R:R 2.2x
   📊 Confidence: 90.0% | Hold: 4.0 days
   ⚡ Auto-Execute: YES

#2 GHV Infra [GHVINFRA.BO] — STRONG_BUY (LONG)
   📰 Multibagger small-cap stock trades green despite stock market sell-off
   🎯 Target: +15.0% | Stop: -7.0% | R:R 2.1x
   📊 Confidence: 90.0% | Hold: 4.0 days
   ⚡ Auto-Execute: YES
```

### Remaining Issues
- Some tickers not in yfinance (SWPEL, RIL) — need manual mapping
- Himadri (HSCL) is ₹40K Cr large-cap — filtered out by large-cap penalty
- Niche sources (Equitymaster, Trendlyne, ValuePickr) return 0 in dev — need production network
- yfinance rate limits on bulk validation — acceptable for on-the-fly use

---

## Universe (75 stocks + on-the-fly expansion)

### Small-Cap (27 stocks, ₹30-800, ₹50-8000Cr)
ASHOKA.NS, BAJAJELEC.NS, COASTCORP.NS, DBL.NS, DELTACORP.NS,
GHCL.NS, HGINFRA.NS, JTEKTINDIA.NS, KALPATARU.NS, MAHLOG.NS,
MANALIPETC.NS, MANINFRA.NS, ORIENTELEC.NS, PNCINFRA.NS,
RAJESHEXPO.NS, SERVOTECH.NS, SPIC.NS, TARSONS.NS, VSTIND.NS,
WEBELSOLAR.NS, RAJRATAN.NS, JYOTHYLAB.NS, THOMASCOOK.NS,
GSFC.NS, NFL.NS, RCF.NS, CLEAN.NS

### Large-Cap (39 stocks, added to catch news)
ICICIBANK.NS, HDFCBANK.NS, AXISBANK.NS, KOTAKBANK.NS, YESBANK.NS,
RELIANCE.NS, TATASTEEL.NS, SBIN.NS, HCLTECH.NS, WIPRO.NS,
INFY.NS, TCS.NS, ITC.NS, HINDUNILVR.NS, BHARTIARTL.NS,
LT.NS, ASIANPAINT.NS, MARUTI.NS, SUNPHARMA.NS, DRREDDY.NS,
CIPLA.NS, BAJFINANCE.NS, BAJAJFINSV.NS, TATACONSUM.NS,
BRITANNIA.NS, NESTLEIND.NS, HEROMOTOCO.NS, BAJAJ-AUTO.NS,
M&M.NS, ULTRACEMCO.NS, ADANIENT.NS, ADANIPORTS.NS,
TATAPOWER.NS, NTPC.NS, POWERGRID.NS, ONGC.NS, BPCL.NS,
HINDPETRO.NS, INDUSINDBK.NS

---

## News Sources (25 Config-Driven)

### Mainstream (8)
| Source | Type | Status |
|--------|------|--------|
| Times of India | RSS+HTML | ✅ |
| The Print | RSS+HTML | ✅ |
| News18 | RSS+HTML | ✅ |
| Indian Express | RSS+HTML | ✅ |
| Financial Express | RSS+HTML | ✅ |
| Business Standard | RSS+HTML | ✅ (aggressive blocking) |
| NDTV | RSS only | ✅ |
| Economic Times | RSS+HTML | ✅ |

### Government (3)
| Source | Type | Status |
|--------|------|--------|
| PIB Defence | RSS+HTML | ✅ |
| PIB Ministry of Defence | RSS+HTML | ✅ |
| DRDO | HTML only | ✅ |

### Market-Specific (7)
| Source | Type | Status |
|--------|------|--------|
| Moneycontrol Markets | RSS+HTML | ✅ |
| Moneycontrol Results | RSS+HTML | ✅ |
| ET Markets | RSS+HTML | ✅ |
| BS Markets | RSS+HTML | ✅ |
| Mint Markets | RSS+HTML | ✅ |
| Tickertape Blog | RSS+HTML | ✅ |

### Niche Small-Cap (6) — NEW
| Source | Type | Status |
|--------|------|--------|
| Equitymaster | RSS+HTML | ⚠️ (needs testing) |
| Value Research | RSS+HTML | ✅ (6 articles) |
| Screener.in | HTML only | ⚠️ (needs testing) |
| Trendlyne | RSS+HTML | ⚠️ (needs testing) |
| ValuePickr | RSS+HTML | ⚠️ (needs testing) |
| BSE SME | HTML only | ⚠️ (needs testing) |

### Corporate (2)
| Source | Type | Status |
|--------|------|--------|
| NSE Announcements | API | ⚠️ (needs nsepython) |
| BSE Corporate Filings | HTML | ✅ |

---

## API Keys (All in .env)
- ✅ Groq (5 keys) — main AI provider
- ✅ OpenRouter — backup
- ✅ Cerebras — backup
- ✅ Gemini — backup
- ✅ NVIDIA NIM — fast inference
- ✅ Telegram Bot — `@AlphaScoutSignals_bot` (Chat ID: 5096981721)
- ❌ Zerodha Kite — needs manual setup

---

## How to Use
```bash
cd D:\Codes\alphascout
source venv/bin/activate

# Run pipeline (sends to Telegram)
python main.py run --signals 3

# Screener-first mode
python main.py scan --signals 3

# Check database stats
python main.py db

# Calibrate confidence from stored outcomes
python main.py calibrate

# Backtest: fetch outcomes + show results
python main.py backtest

# Backtest: resolve outcomes only
python scripts/backtest.py resolve --days 30

# Backtest: replay pipeline on stored articles
python scripts/backtest.py replay --days 30 --max-signals 10

# Backtest: show results only
python scripts/backtest.py results

# Check universe
python -c "from src.universe.builder import get_universe; u = get_universe(); print(f'{len(u)} stocks')"
```

---

## What to Do Next (Priority Order)

### Phase 1: Database & Logging ✅ DONE
- SQLite storage with 4 tables is live
- All pipeline stages write to DB

### Phase 2: Backtesting Harness (Next)
- Rewrite `scripts/backtest.py` to read from DB
- Fetch actual price outcomes from yfinance
- Compute win rate, R-multiple, max drawdown, Sharpe-like ratio

### Phase 3: Confidence Calibration
- Create `src/analysis/calibration.py`
- Bucket signals by stated confidence, compare to outcomes
- Remap to calibrated confidence before auto-execution

### Phase 4: Source Trust Tiers & PR/Pump Filters
- Add `tier` field to all sources in `config/sources.yaml`
- Update prompts to flag promotional language and require independent confirmation

### Phase 5: Portfolio Risk Rules
- Fix `manager.py` bug (`self.mapper`)
- Add min daily traded value filter, max drawdown kill-switch
- `PERSONAL_USE_ONLY` flag, hard position sizing limits

### Phase 6: Universe Construction Rules
- Rule-based inclusion from `config/settings.yaml`
- Universe change logging

### Phase 7: Auto-Execution Guard
- `PERSONAL_USE_ONLY = true` flag
- Paper-trading only until 2-3 months of signals logged

---

## Key Files Modified

### Session 3
- `src/ai/providers.py` — Added dotenv loading at import
- `src/universe/ticker_map.py` — Fixed false positive matching (word boundary)
- `src/analysis/pipeline.py` — Added small-cap keyword pre-filter
- `src/scraping/scraper.py` — Removed dead sources, added Tickertape/BSE
- `data/universe_cache.json` — 66 stocks
- `.env` — Telegram credentials added

### Session 4
- `src/scraping/scraper.py` — **Refactored to config-driven** (reads from `sources.yaml`)
- `config/sources.yaml` — **Added 6 niche small-cap sources** + expanded to 25 total

### Session 6
- `.gitignore` — Created (excludes venv, .env, data/*.json, __pycache__, credentials)
- `SESSION_MEMORY.md` — Updated with GitHub setup

### Session 7 — Phase 1 (Database)
- `src/storage/__init__.py` — **NEW** — Package init
- `src/storage/db.py` — **NEW** — SQLite storage module (4 tables, CRUD, stats)
- `src/scraping/scraper.py` — Wired articles to DB storage
- `src/analysis/pipeline.py` — Wired LLM analyses and signals to DB
- `main.py` — Added `db` command for database stats

### Session 7 — Phase 2 (Backtesting)
- `scripts/backtest.py` — **Rewritten** — Full backtest harness (resolve/replay/results)
- `main.py` — Updated backtest command to use new module

### Session 7 — Phase 3 (Calibration)
- `src/analysis/calibration.py` — **NEW** — ConfidenceCalibrator with 5 buckets
- `src/analysis/pipeline.py` — `_format_output()` now includes calibrated confidence
- `main.py` — Added `calibrate` command, updated signal display

### Session 7 — Phase 4 (Source Tiers & PR/Pump)
- `config/sources.yaml` — Added `tier` field to all 25 sources
- `src/ai/prompts.py` — Added PR/pump detection to triage prompt
- `src/analysis/pipeline.py` — Added pr_pump_risk filtering (HIGH=reject, MEDIUM=penalty)
- `src/scraping/scraper.py` — Source tier now carried in article data

### Session 7 — Phase 5 (Portfolio Risk)
- `config/settings.yaml` — Added `portfolio` section (personal_use_only, paper_trading, sizing limits, drawdown)
- `src/portfolio/manager.py` — **Rewritten** — Fixed mapper bug, added all safety constraints

### Session 7 — Phase 6 (Universe Rules)
- `config/settings.yaml` — Added `min_avg_daily_value_cr`, `log_changes`, `exclude_sebi_asm/gsm`
- `src/universe/builder.py` — Rule-based filters from config, universe change logging

---

## Quick Test Commands
```bash
cd /home/neo/Codes/alphascout
source venv/bin/activate

# Full pipeline run
python main.py run --signals 3

# Check what's in news vs universe
python -c "
from src.scraping.scraper import scrape_all_sources
from src.universe.ticker_map import extract_tickers
from src.universe.builder import get_universe
universe = get_universe()
articles = scrape_all_sources(use_cache=False)
for a in articles[:10]:
    tickers = extract_tickers(f'{a.title} {a.summary}')
    matches = [t for t in tickers if t in universe]
    print(f'{'✅' if matches else '❌'} {a.title[:50]} -> {matches}')
"

# Git commands
git status                    # Check working tree status
git add .                     # Stage all changes
git commit -m "message"       # Commit changes
git push                      # Push to GitHub
git pull                      # Pull from GitHub
```
