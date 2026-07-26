# AlphaScout v1.0

**Multi-Sector Small-Cap News → Trade Signal Bot for Indian Markets**

AlphaScout scrapes 25 Indian news sources, analyzes articles via an AI ensemble of 6 LLM providers, and generates buy/sell signals for small-cap stocks with automated Telegram delivery.

## Features

- Scrapes 25 Indian news sources (mainstream, government, market-specific, niche small-cap, corporate)
- AI ensemble analysis using 6 providers (Groq, Cerebras, OpenRouter, Gemini, NVIDIA NIM)
- Universe of 75 small/mid-cap stocks + on-the-fly expansion via yfinance
- Generates buy/sell signals with minimum 2:1 risk-reward ratio
- Screener-first mode (NSE gainers → Screener.in → Trendlyne → match to news)
- Telegram signal delivery via `@AlphaScoutSignals_bot`
- 3-7 day holding period, min 10% upside target
- Auto-execute trades at 90%+ confidence
- 2x daily scheduler (6:30 AM & 4:30 PM IST)

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

# Start the 2x daily scheduler
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

## Project Structure

```
alphascout/
├── main.py                  # Entry point
├── config/
│   ├── providers.yaml       # AI provider configs
│   ├── sectors.yaml         # Sector definitions
│   ├── settings.yaml        # Trading rules & thresholds
│   └── sources.yaml         # 25 news source configs
├── src/
│   ├── ai/
│   │   ├── ensemble.py      # AI ensemble analysis
│   │   ├── prompts.py       # LLM prompts
│   │   └── providers.py     # 6 AI provider integrations
│   ├── analysis/
│   │   └── pipeline.py      # Article → Signal pipeline
│   ├── portfolio/
│   │   ├── manager.py       # Portfolio & position tracking
│   │   └── telegram.py      # Telegram delivery
│   ├── scraping/
│   │   └── scraper.py       # Config-driven news scraper
│   ├── screening/
│   │   └── screener.py      # NSE/Screener/Trendlyne screener
│   ├── signals/
│   │   └── notifier.py      # Signal notifications
│   ├── universe/
│   │   ├── builder.py       # Universe builder + on-the-fly expansion
│   │   └── ticker_map.py    # Ticker extraction & mapping
│   └── config.py            # Config loader
├── scripts/
│   ├── backtest.py          # Backtesting
│   ├── setup_credentials.py # Credential setup wizard
│   └── setup_ve_keys.py     # Voting Exchange keys
├── requirements.txt
└── .env                     # API keys (not committed)
```

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

## How It Works

1. **Scrape** — Fetches articles from 25 Indian news sources (RSS + HTML)
2. **Extract** — Identifies stock tickers mentioned in articles
3. **Match** — Cross-references tickers against the 75-stock universe
4. **Analyze** — Sends matched articles through the AI ensemble (6 LLM providers)
5. **Signal** — Generates buy/sell signals with confidence, targets, and stop-losses
6. **Deliver** — Sends qualifying signals to Telegram

## License

Private — All rights reserved.
