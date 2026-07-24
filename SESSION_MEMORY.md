# AlphaScout Session Memory
**Last Updated:** 2025-07-24 (Session 6)
**Project Root:** `/home/neo/Codes/alphascout`

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

## Current Status: PRODUCTION-QUALITY PIPELINE

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
cd /home/neo/Codes/alphascout
source venv/bin/activate

# Run pipeline (sends to Telegram)
python main.py run --signals 3

# Check universe
python -c "from src.universe.builder import get_universe; u = get_universe(); print(f'{len(u)} stocks')"

# Test providers
python -c "from src.ai.providers import ProviderRegistry; reg = ProviderRegistry(); print(list(reg.providers.keys()))"
```

---

## What to Do Next (Priority Order)

### 1. Test Niche Sources in Production
Run `python main.py run --no-cache --signals 3` in a real environment to verify:
- Equitymaster, Trendlyne, ValuePickr RSS feeds work
- Screener.in and BSE SME HTML scraping works
- Niche sources actually produce small-cap articles

### 2. Fix Niche Sources That Failed
If any niche sources return 0 articles:
- Try alternative RSS URLs
- Switch to HTML scraping with different selectors
- Check if sites block automated requests

### 3. Groq Rate Limit Issue
- Groq free tier: 100K tokens/day
- We hit limit today (~50 articles = ~100K tokens)
- **Fix**: Use Cerebras/OpenRouter/Gemini more, reduce article count, or get more API keys

### 4. GitHub Actions CI/CD (Optional)
- Add `.github/workflows/` for automated testing
- Set up scheduled runs (e.g., daily market scan at 9:30 AM IST)

### 5. Remaining Features
- Zerodha integration (needs API keys)
- Backtesting (need more signals first)
- Scheduler testing

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
