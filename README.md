# AlphaScout v1.0

**Multi-Sector Small-Cap News → Trade Signal Bot for Indian Markets**

AlphaScout scrapes 25 Indian news sources, analyzes articles via an AI ensemble of 6 LLM providers, and generates buy/sell signals for small-cap stocks with automated Telegram delivery.

## Features

- Scrapes 25 Indian news sources (mainstream, government, market-specific, niche small-cap, corporate)
- AI ensemble analysis using 6 providers (Groq, Cerebras, OpenRouter, Gemini, NVIDIA NIM)
- Universe of 75+ small/mid-cap stocks built from Screener.in filters + on-the-fly expansion via yfinance
- **NSE/BSE company name lookup table** (~200+ entries) for accurate article-to-ticker matching
- Generates buy/sell signals with minimum 2:1 risk-reward ratio
- Screener-first mode (NSE gainers → Screener.in → Trendlyne → match to news)
- **Intra-day spike scanning** every 15 min during market hours (9:15 AM – 3:30 PM IST)
- Telegram signal delivery via `@AlphaScoutSignals_bot`
- 3-7 day holding period, min 10% upside target
- Auto-execute trades at 90%+ confidence
- 2x daily scheduler (6:30 AM & 4:30 PM IST) + intra-day spike scans
- **Hard SEBI personal-use gate** — blocks non-personal mode without explicit env-var acknowledgement
- **Daily LLM budget ceiling** — graceful degradation when free-tier quotas are exhausted
- Confidence calibration from historical outcomes
- Circuit history check — penalizes stocks with recent lower-circuit hits
- PR/pump detection — company PR alone never triggers a signal

## Quick Start

```bash
# Clone the repo
git clone https://github.com/Abpattar/alphascout.git
cd alphascout

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Set up API keys
cp .env.example .env
# Edit .env with your API keys (at minimum, add a Groq key)
```

## Usage

```bash
# Run the full pipeline (scrape → analyze → signal → Telegram)
python main.py run --signals 3

# Run screener-first mode
python main.py scan --signals 5

# Run without cache (fresh scrape)
python main.py run --no-cache --signals 3

# Start the scheduler (2x daily + intra-day spike scans)
python main.py scheduler

# Run backtest
python main.py backtest

# View portfolio
python main.py portfolio

# View config
python main.py config

# Test AI providers
python main.py test

# Run credential setup wizard
python main.py --setup
```

### SEBI Compliance Gate

When `portfolio.personal_use_only` is set to `false` in `config/settings.yaml`, the bot requires an environment variable to confirm you have reviewed SEBI regulations:

```bash
# Windows PowerShell
$env:I_HAVE_REVIEWED_SEBI_REGULATIONS="true"
python main.py run

# Linux/Mac
I_HAVE_REVIEWED_SEBI_REGULATIONS=true python main.py run
```

Without this variable, the bot will **refuse to start** in shared mode.

### LLM Budget Configuration

Budget ceilings are configured in `config/settings.yaml` under `llm_budget`:

```yaml
llm_budget:
  daily_token_budget: 120000   # ~100K Groq free-tier + buffer
  daily_call_budget: 300       # absolute max LLM calls/day
  per_run_token_budget: 40000  # max tokens per single pipeline run
  per_run_call_budget: 80      # max LLM calls per single pipeline run
```

When the budget is hit, the pipeline returns partial results and logs a warning instead of crashing.

## Project Structure

```
alphascout/
├── main.py                  # Entry point, scheduler, CLI
├── config/
│   ├── nse_bse_tickers.json # NSE/BSE company name→ticker lookup (~200+ entries)
│   ├── providers.yaml       # AI provider configs
│   ├── sectors.yaml         # Sector definitions
│   ├── settings.yaml        # Trading rules, LLM budget, scheduler config
│   └── sources.yaml         # 25 news source configs
├── src/
│   ├── ai/
│   │   ├── ensemble.py      # AI ensemble analysis
│   │   ├── prompts.py       # LLM prompts (4-stage pipeline)
│   │   └── providers.py     # 6 AI provider integrations + budget tracking
│   ├── analysis/
│   │   ├── calibration.py   # Confidence calibration from outcomes
│   │   └── pipeline.py      # 4-stage Article → Signal pipeline
│   ├── portfolio/
│   │   ├── manager.py       # Portfolio & position tracking
│   │   └── telegram.py      # Telegram delivery (personal-use enforcement)
│   ├── scraping/
│   │   └── scraper.py       # Config-driven news scraper
│   ├── screening/
│   │   └── screener.py      # NSE/Screener/Trendlyne + spike detection
│   ├── signals/
│   │   └── notifier.py      # Signal notifications
│   ├── universe/
│   │   ├── builder.py       # Universe builder + on-the-fly expansion + safety filters
│   │   └── ticker_map.py    # Ticker extraction, mapping, aliases
│   └── config.py            # Config loader
├── scripts/
│   ├── backtest.py          # Backtesting + auto-outcome resolution
│   ├── setup_credentials.py # Credential setup wizard
│   └── setup_ve_keys.py     # Voting Exchange keys
├── data/                    # Runtime data (gitignored)
│   ├── daily_llm_stats.json # Daily LLM budget tracking
│   ├── spike_queue.json     # Intra-day spike scan queue
│   └── unresolved_candidates.jsonl  # Unresolved company names for review
├── requirements.txt
└── .env                     # API keys (not committed)
```

## Architecture

### 4-Stage LLM Pipeline

1. **Quick Filter** — Rejects articles unrelated to our 10 sectors (uses Groq 8B for speed)
2. **Triage** — Detects catalyst type, strength, time sensitivity, PR/pump risk
3. **Entity Extraction** — Identifies companies mentioned, extracts financial details
4. **Impact Analysis** — Predicts price direction, magnitude, and confidence per stock

### Pre-Filter (Issue 1: Real NSE/BSE Lookup)

Articles are filtered before entering the LLM pipeline using a three-layer check:
1. **Universe tickers** — Fast check against the live 75-stock universe
2. **NSE/BSE lookup** — Checks against ~200+ known company names/aliases from `config/nse_bse_tickers.json`
3. **Small-cap keywords** — Catch-all for articles mentioning small-cap stocks not yet in the lookup

### Intra-Day Spike Scanning (Issue 2)

- Runs every 15 minutes during market hours (9:15 AM – 3:30 PM IST)
- Scans the universe for unusual price/volume spikes using yfinance
- Queues spiking tickers into `data/spike_queue.json`
- Mini-analysis pass scrapes news only for queued tickers (lightweight, no full re-scrape)

### SEBI Personal-Use Gate (Issue 3)

- `config/settings.yaml` → `portfolio.personal_use_only: true` (default)
- When set to `false`, startup is **blocked** unless `I_HAVE_REVIEWED_SEBI_REGULATIONS=true` env var is set
- Telegram delivery refuses to send to any chat_id other than the configured one in personal-use mode

### Daily LLM Budget Ceiling (Issue 4)

- Budget loaded from `config/settings.yaml` → `llm_budget` section
- Daily stats persisted to `data/daily_llm_stats.json` (resets on date rollover)
- Checked before every provider call in `execute_with_fallback`
- Raises `BudgetExhaustedError` when all providers are exhausted; pipeline catches it and returns partial results

### Risk Management

- `passes_stock_safety_filter()` — shared function used everywhere (universe build, on-the-fly validation, pipeline impact analysis)
- `check_circuit_history()` — penalizes confidence on recent circuit hits
- PR/pump detection — requires independent source confirmation; MEDIUM risk rejected from Tier 3-4 sources
- Auto-outcome resolution scheduled at 9:30 AM IST daily (yfinance price check)

## API Keys

Required (at minimum):
- **Groq** — Primary AI provider (free tier: 100K tokens/day)

Optional backups:
- **Cerebras** — Backup AI provider
- **OpenRouter** — Backup AI provider
- **Gemini** — Backup AI provider
- **NVIDIA NIM** — Fast inference

Optional integrations:
- **Telegram Bot** — Signal delivery (`@AlphaScoutSignals_bot`)
- **Zerodha Kite** — Auto-execution (needs manual setup)

## 10 Sectors

| Sector | Examples |
|--------|----------|
| Defence | Data Patterns, HAL, BEL, Paras Defence |
| Railways | RVNL, IRFC, IRCTC, Titagarh, Jupiter Wagons |
| EV | Olectra, JBM Auto, Exide, Amara Raja |
| Renewables | Waaree, Suzlon, Inox Wind, Borosil Renewable |
| Infra | KEC, Kalpataru, PNC Infra, HG Infra, Dilip Buildcon |
| Pharma | Dr Reddy's, Cipla, Laurus Labs, Granules |
| Chemicals | Navin Fluorine, PI Industries, SRF, Deepak Nitrite |
| Logistics | Delhivery, Blue Dart, VRL Logistics, TCI |
| Manufacturing | Dixon, Amber, Kaynes, Netweb, Syrma |
| IT | Cyient, Coforge, Birlasoft, Persistent Systems |

## License

Private — All rights reserved.
