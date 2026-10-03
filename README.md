# AlphaScout

Indian-market news intelligence. Finds genuinely new, material news about
Indian listed companies, verifies the company against a real NSE/BSE listing,
pulls **real** market data, computes trade levels with deterministic maths, uses
AI only for interpretation, and sends at most **3** signals per run to Telegram.

> **Nothing is invented.** If market data is unavailable the signal is dropped.
> If an article has no trustworthy publication timestamp it is not treated as
> new. If the AI fails, nothing is sent. Fewer signals is the correct outcome.

---

## Schedule

| Time (IST) | What runs |
|---|---|
| **04:00** | Main scan — overnight news |
| 04:20 | Watchdog — re-dispatches if the 04:00 run was skipped by GitHub |
| **07:00** | Main scan — pre-market news |
| 07:20 | Watchdog — re-dispatches if the 07:00 run was skipped |

Cron expressions carry an explicit `timezone: "Asia/Kolkata"`, so `0 4 * * *`
means 04:00 **Indian** time (22:30 UTC), not 04:00 UTC.

Both main runs happen **before the Indian market opens**, so every price is
labelled `PREVIOUS CLOSE`. The system will never call a stale price live.

---

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # add your keys

python main.py health         # store + credentials + market session
python main.py run --dry-run  # full pipeline, prints, sends nothing
python main.py state          # what we remember from previous runs
```

### Commands

| Command | Purpose |
|---|---|
| `run` | Full pipeline; sends up to 3 signals |
| `run --dry-run` | Everything except the Telegram send; writes no state |
| `scan` | As `run`, but only stocks a live screener currently flags |
| `state` | Persistent store contents and recent signals |
| `health` | Store reachability, credentials, market session |
| `backtest` / `db` / `holds` / `calibrate` / `config` | Supporting tools |

---

## How a signal is built

```
scrape 25 sources
   → freshness gate      (publication timestamp must be real and recent)
   → opinion/listicle filter
   → cross-source clustering   (one story, many outlets → one candidate)
   → persistent-history dedup  (already sent? → drop)
   → developing-story check    (genuinely new development? → allow)
   → verified Indian ticker    (name → NSE/BSE, confirmed against a real listing)
   → real market data          (yfinance quote + 6 months of OHLCV)
   → computed indicators       (SMA20/50, RSI-14, ATR-14, swing support/resistance)
   → AI assessment             (material? direction? prose — NO numbers)
   → deterministic levels      (entry = last real close; stop = 2×ATR; target = swing)
   → validation gate           (can only veto)
   → ≤3 signals → Telegram
```

### Facts vs calculation vs interpretation

The Telegram message labels every section, because the distinction matters:

| Label | Meaning | Source |
|---|---|---|
| `MARKET DATA (from market feed)` | price, previous close, volume, market cap | yfinance |
| `CALCULATED (computed from real prices)` | entry, target, stop, risk/reward, RSI, SMA, ATR | this code |
| `AI ASSESSMENT (interpretation, not data)` | catalyst, thesis, watchpoint, risk | language model |

**The AI is never allowed to produce a number.** The prompt schema contains no
price, percentage or indicator fields, the client strips 20 forbidden numeric
keys from any response, and the validator rejects a signal whose AI block
contains one. Entry must equal the real reference price — if the model tries to
set it, the signal is dropped.

---

## Trade level method (`atr_swing_v1`)

Stated explicitly so it can be checked:

- **entry** — the last real close. Not a prediction.
- **stop** — `2 × ATR(14)` from entry, floored at 1.5% of price, and widened to
  the 20-bar swing low only when that stays inside the 12% risk cap.
- **target** — the larger of `2 × risk` and the distance to the 20-bar swing
  resistance, capped at `3 × risk`.
- **risk/reward** — recomputed from the rounded levels. Never taken from the
  model. Rejected below 1.8.

---

## Deduplication

Three layers, in order of confidence:

1. **Canonical URL** — strips `utm_*`, `fbclid`, `amp` variants, `www.`,
   `m.` mobile hosts, trailing slashes.
2. **Cross-source clustering** — within a run, articles are clustered by a
   composite score (content-word overlap + material-figure overlap + edit
   distance). "Company X announces Rs 10,000 crore investment" and "Company X
   to invest Rs 10000 crore in expansion" merge into one story, keeping the
   highest-tier outlet as the headline source and the rest as corroboration.
3. **Cross-run story matching** — against every story already delivered. A
   headline qualifies as a repeat on URL, on normalised headline, or on
   composite similarity ≥ 0.62.

### Repeat vs genuinely new development

Both must be true to be treated as a new development:

1. same **event category** (regulatory / order / earnings / capex / M&A /
   fundraising / management / product / rating / policy), **and**
2. a new or escalated action within that category, **and**
3. new information — a material figure the earlier headline did not contain.

So *"X receives SEBI notice"* → *"SEBI orders X to pay Rs 250 crore penalty"*
is delivered as new information, while *"Lupin Q2 profit rises"* →
*"Lupin wins USFDA nod"* is **not** (different categories, same company only).

---

## Persistence

AlphaScout runs on ephemeral GitHub runners, so anything in `data/` is
destroyed when the job ends. All memory therefore lives in a `StoryStore`,
selected at startup:

| Backend | When | How it survives |
|---|---|---|
| `git-state` (default) | always available | `state/*.jsonl` committed back to the repo by the workflow |
| `supabase` | `SUPABASE_URL` + `SUPABASE_KEY` set | PostgreSQL via PostgREST |

Force with `ALPHASCOUT_STORE=git|supabase`. Both implement the same interface;
there is one production code path.

Tables/rows: `articles` (canonical URL, title, fingerprint, published, first
seen, sent flag), `stories` (event key, sent count, development index,
corroborating sources), `signals` (ticker, real market price used, calculated
levels, indicators, AI text, sent flag).

Retention is bounded — articles 120 days, stories and signals 365.

> **This is the fix for the system's central defect.** Previously the SQLite
> database was gitignored and never committed, so every run started empty:
> deduplication, the per-ticker cooldown, confidence calibration and
> backtesting were all silently dead in production.

---

## Configuration

`.env` (see `.env.example`):

```
GROQ_API_KEY, GROQ_API_KEY_2..8   # rotated round-robin; shared org bucket
OPENROUTER_API_KEY, CEREBRAS_API_KEY, GEMINI_API_KEY, NVIDIA_NIM_API_KEY
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
SUPABASE_URL, SUPABASE_KEY         # optional; enables the Postgres backend
```

`config/`: `sources.yaml` (25 sources + keywords), `settings.yaml` (budgets,
filters, risk limits), `nse_bse_tickers.json` (297 name→ticker),
`sectors.yaml` (sector keywords).

Optional env: `ALPHASCOUT_STORE`, `ALPHASCOUT_LOG_LEVEL`,
`ALPHASCOUT_FORCE_IPV4=0`, `ALPHASCOUT_INSECURE_TLS=1` (escape hatch only —
TLS verification is **on** by default).

---

## Cost

Free tiers only. Market data via Yahoo Finance (unofficial), news via public
RSS/HTML, AI via the free tiers of Groq / Cerebras / Gemini / OpenRouter /
NVIDIA NIM, storage via git or Supabase's free tier. No paid API is required.

---

## Tests

```bash
python -m pytest tests/ -q
```

145 tests, no network required. They cover the scenarios that actually broke
production:

- the duplicate lifecycle (run 1 sends, run 2 suppresses, a new development is
  allowed, cross-source merging, developing stories)
- indicator maths against hand-computed and independently recomputed values
- **negative** tests that a missing price, missing history or missing ATR
  produces a rejection rather than a default
- validation vetoes (unverified ticker, stale article, invented entry, AI
  numeric fields)
- Telegram formatting with hostile `<`/`&`/quote content and length limits
- news-quality filtering of opinion pieces and listicles
- dry-run isolation (writes no state)

---

## Known limitations

- **TATAMOTORS.NS and TATAMTRDVR.NS currently return no data from Yahoo
  Finance.** The system refuses to invent a price, so signals for those two
  symbols are dropped rather than fabricated. NSE's public API blocks
  datacenter IPs (HTTP 403) and Stooq does not cover Indian equities, so there
  is no verified free fallback.
- Roughly 40% of scraped articles arrive without a publication timestamp and
  are discarded as unverifiable. Dates are recovered from page metadata for the
  top 40 enriched articles; raising `scraping.enrich_top_n` widens this at the
  cost of more HTTP requests.
- Yahoo Finance is an unofficial interface and occasionally rate-limits.
- The 20-bar swing support/resistance method is deliberately simple, not
  order-book derived.
