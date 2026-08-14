# AlphaScout Session Memory
**Last Updated:** 2026-08-14 (Session 12)
**Project Root:** `/home/neo/Codes/alphascout` (Linux; was `D:\Codes\alphascout` on Windows)

---

## Session 12 (2026-08-14) — Commit Session 11 + first real wins on the new budget

### What we did
1. ✅ **Committed + pushed Session 11** (`192078a`, 7 files, +743/−19) — holdings/reminder feature + LLM budget bump are now on GitHub. Working tree clean (only `data/` untracked, fully gitignored).
2. ✅ **Full live run confirmed the budget reset works** — `main.py run --signals 5`:
   - **Auto-resolved the 4 stale Aug-10 signals → first real wins**: CUPID.NS +15.0% (WIN, target hit), AARTIPHARM.NS +12.56% (WIN), UTLSOLAR.BO +5.63% (HOLD), CYIENT.NS +2.12% (HOLD). 2W / 0L / 2H on these.
   - **2 new signals delivered to Telegram** (both sent OK): JTEKTINDIA.NS WATCH 72% (implied beneficiary, manufacturing), PRAJIND.NS BUY 76% (newly discovered company, entry break ₹340).
   - **Usage**: 84 LLM calls / ~58.8K est tokens — only 6% of the new daily budget (1416 calls left, 1.34M tokens left). No budget issues; rate limits (8 Groq keys) remain the real ceiling.
   - Pipeline discipline held: 3 trades rejected on honest R:R < 1.5 (IDEAFORGE, APOLLO, PGEL, DEVIT), TATATECH name/ticker mismatch guard fired again, circuit-risk penalty on IDEAFORGE, non-Yahoo stocks (PARASDEF, ZENTEC, BHARATFORG, WABCO, DIXON) correctly discarded.
   - Only 3 LLM errors across 84 calls (1 cerebras, 1 gemini timeout, 1 openrouter JSON-parse — all gracefully retried/absorbed).

### Current state
- 6 signals in DB (2 today), 4 outcomes (2 WIN / 2 HOLD), 0 holdings, all committed & pushed.
- LLM budget: 1.5M tokens / 1500 calls/day (new).
- DB stats show first real accuracy data (4 resolved outcomes).

### Suggested next steps (continue here)
1. Keep the scheduler running (`python main.py scheduler`) so buttons/reminders work; test the buy→7d→30d lifecycle on a real holding via Telegram.
2. Let today's signals (JTEKTINDIA.NS, PRAJIND.NS) age past 1 day → auto-resolve on next run → win rate/calibration updates.
3. As outcomes accumulate, re-check calibration buckets (calibrate command) — current data still sparse (4 outcomes).

---

## Session 11 (2026-08-10) — Manual Buy/Sell Tracker + Reminders + LLM Budget Scale-Up

### What we did
1. ✅ **Repo sync + environment move** — machine is now Linux (`/home/neo/Codes/alphascout`, `venv/bin/python` = Python 3.12). Local folder was ~13 commits / ~5,400 lines behind GitHub; synced to `main` (commit `c4d5569`, Sessions 7–10 all present). Stale caches deleted (`articles_cache.json`, `universe_cache.json`, `backtest_20260719.json`); `data/.credentials/` kept.
2. ✅ **Strategy decision (user): MANUAL trading, no auto-execute** — user buys/sells in their own broker; the bot only *sends signals* with Telegram buttons. No Zerodha/Kite (still ❌ in key checks, by design). No cloud hosting for now — buttons/reminders only work while `python main.py scheduler` runs on this PC.
3. ✅ **Built the holdings / reminder system** (all files tested end-to-end):
   - `src/storage/db.py` — new `holdings` table + CRUD: `store_holding`, `get_holdings`, `get_holding`, `get_holding_by_signal`, `mark_holding_sold` (computes pnl/pnl_pct), `extend_holding`, `mark_holding_reminded`, `reset_holdings_nudges`, `delete_holding`. Stats now include `holdings_open` / `holdings_sold`.
   - `src/portfolio/telegram.py` — `send_message` gains `reply_markup`; new `make_inline_keyboard`, `answer_callback_query`, `edit_message_reply_markup`; `send_signal` attaches `bought:{signal_id}` / `skip:{signal_id}` buttons.
   - `src/portfolio/bot.py` (**NEW**) — long-polling `poll_updates()` (offset-based, 25s timeout), callback handlers (`bought:`/`skip:`/`sold:`/`extend:`), pending-input state machine (buy price → qty; sell price), `run_reminder_check()` (fires only on `reminder_days`, max `nudges_per_day`, deduped by date), `fetch_current_price()` via yfinance, `_send_holdings_list` for `/holds`.
   - `src/config.py` — `get_holdings_config()`; `config/settings.yaml` — `holdings:` block: `reminder_days: [7, 30]`, `nudges_per_day: 2`, `patience_days: 30`, `extend_days: 30`.
   - `main.py` — `scheduled_reminders()` + `bot_poll_loop()` jobs; `holds` CLI command; `run_scheduler` rewritten to `async def` + `await asyncio.Event().wait()` (old `asyncio.get_event_loop().run_forever()` crashed with "This event loop is already running").
   - Fixed `CronTrigger` bug: `minute=[0,30]` → `minute="0,30"` (list of ints crashed APScheduler).
4. ✅ **End-to-end tests passed**: buy flow via real signal (stored with sell_due +7d, patience +30d), reminder fired with live price ₹823 + P&L, dedupe caps at 2 nudges/day, sell flow recorded +₹820/+9.9%. All test rows cleaned up. `py_compile` clean; scheduler boots 5 jobs + polling.
5. ✅ **LLM budget scaled for 8 Groq keys** (`config/settings.yaml` → `llm_budget:`): daily_token_budget 120K → **1.5M**, daily_call_budget 300 → **1500**, per_run_token_budget 40K → **300K**, per_run_call_budget 80 → **400**. NOTE: per-run values are loaded but NOT enforced in `_check_budget()` (only daily `calls`/`tokens` are checked) — per-run is aspirational.
6. ✅ **Budget mechanics learned**: stats persist in `data/daily_llm_stats.json`; reset happens automatically on date rollover (keyed by `%Y-%m-%d`); **deleting the file resets manually** (did this today). Token accounting uses `_record_call(estimated_tokens=max_tokens)` — successful calls count the stage's `max_tokens` (up to 2500), failures/rate-limits count 700. A full run ≈ 60–70 calls ≈ ~120K est tokens. Budget exhaustion raises `BudgetExhaustedError` → all articles "fail" → 0 signals (NOT a scraping problem).

### Current state
- 4 unresolved signals in DB from today's first live run: CUPID.NS 76%, AARTIPHARM.NS 80%, UTLSOLAR.BO 50%, CYIENT.NS 61% (3 delivered to Telegram).
- LLM budget reset + raised — ready for more runs.
- **Working tree NOT committed** (holdings feature + budget bump) — pending user's "say the word".

### Caveat
- Reminders/buttons are best-effort: only fire while the scheduler process is running. 3rd-party price fetch (yfinance) can fail on market-holiday/after-hours timings — handled gracefully.
- The 8 Groq keys (rate limits) are the effective ceiling now, not the daily budget.

### Suggested next steps (continue here)
1. Commit + push Session 11 changes (ask user first).
2. Run `venv/bin/python main.py run --signals 5` to confirm signals flow again after budget reset.
3. Keep scheduler running (`python main.py scheduler`) so buttons + reminders work; test the full buy→7d→30d lifecycle with a real holding.
4. Let signals accumulate → outcome resolution (auto-runs with every `run`/`scan`) → real accuracy numbers.

---

## Session 10 (2026-08-04) — Trade-Plan Validation + Outcome Resolution (first real accuracy data)

### What we did
1. ✅ **Fixed the highest-impact data-quality bugs** before trusting accuracy numbers: LLM trade plans were reaching the DB invalid (inverted target/stop, entry=0, garbage thesis like 'x'). Added `AnalysisPipeline._validate_trade_plan()` (`src/analysis/pipeline.py`) which:
   - Rejects LONG target<=entry / stop>=entry, NEUTRAL direction, entry<=0 (falls back to current price), target_pct out of 2–40, stop_pct<=0 or >15, recomputed R:R < 1.5.
   - **Honest R:R recompute** — LLM-claimed R:R is systematically inflated (a 12%/6% plan is really ~2x, but typical 10%/7% plans are ~1.4x). Floor 1.5 in code (config `min_risk_reward_ratio: 2.0` would starve the pipeline). Stored `trade.risk_reward_ratio` is now the honest recomputed value.
   - Rejects garbage thesis (`_GARBAGE_THESIS`: x, n/a, test…) and normalises numeric levels to plain strings (outcomes depend on a non-zero `entry_price`).
   - Verified live: today's run stored `CYIENT.NS entry=820 target=798 stop=918` (inverted) and `PNCINFRA.NS entry=0` — both now impossible.
2. ✅ **Non-stock entity guard** — `_NON_STOCK_ENTITIES` (drdo, isro, barc, sebi, indian navy, mod, …) discarded in `_analyze_impact` before ticker reconciliation, even if a ticker is attached.
3. ✅ **Per-ticker signal cooldown** — `_signal_in_cooldown(output, hours=48)` wired into `analyze_article` before `db.store_signal` (uses existing `db.get_recent_signals`). Stops duplicate-signal spam across runs.
4. ✅ **Purged 5 garbage signals from DB** (user-approved): TATATECH.NS (MTAR Tech), WAAREE.BO ×2 (Zen Tech), DEVIT.NS (DRDO), PNCINFRA.NS (entry=0). 20 signals remain.
5. ✅ **First real outcome resolution** — 16/20 signals resolved via yfinance (`scripts/backtest.py resolve --days 30`), 4 skipped (same-day, too fresh). 3 wins, 2 losses, 11 holds.
   - **Wins**: IDEAFORGE.NS 50% conf (+3.1%), APOLLO.BO 60% (+5.6%), DEVIT.NS 59% (+8.2%).
   - **Losses**: ZENTEC.NS 72% conf (−7.8%, stop hit), DATAPATTNS.NS 72% (−3.4%, stop hit).
   - **Key finding**: high LLM confidence is NOT reliable — the only two 70s-bucket signals BOTH lost; win rate 18.8% (3/16), expectancy −3.48%, PF 1.51.
6. ✅ **Auto-resolution on every run** — `main.py::auto_resolve_outcomes()` now calls `resolve_outcomes` + recalibrates at the start of `run_pipeline()` and `run_screener_pipeline()` (best-effort, never raises, min_age 1 day). Outcomes now accumulate even without a 24/7 scheduler.
7. ✅ **Calibration now real-data driven** — `python main.py calibrate`: 60-69 bucket (12 sigs) → 25%→calibrated 30%; 70-79 (4 sigs) → 0%→30% floor. Auto-execute effectively gated off (no bucket reaches 80%).

### Session 10 follow-up fixes (same day) — cleaned up before new work
1. ✅ **Wired Session-8 backtest winners into the live screener** (`src/screening/screener.py::scan_price_volume_spikes`): price-driven spikes (both > price > volume) rank first; volume-only spikes capped to `screening.volume_only_spike_max_share` (25%) so they can't crowd out price spikes; priority sectors (`defence`, `railways`, `manufacturing_pli`) tie-break. `ScreenerCandidate` gained `sector` + `spike_type`; `main.py` now passes `universe` for sector lookup. Config in `config/settings.yaml` (`screening:`) + `src/config.py::get_screening_config()`.
2. ✅ **Deduplicated outcomes before calibration/results** (`src/storage/db.py`): `get_all_outcomes()` and `get_outcomes_for_calibration()` now collapse same-ticker/same-day signals (highest confidence, tie-break earliest) — 16 raw → 10 independent signals. `show_results` prints the collapse count. Prevents pre-cooldown duplicates (5× DEVIT, 4× APOLLO, 3× IDEAFORGE) biasing win-rate/calibration.
3. ✅ **Wired `signals.min_risk_reward_ratio` config** into `_validate_trade_plan` (was a dead config; code hardcoded 1.5). Value set to **1.5** in `config/settings.yaml` (was misleading 2.0 — an honest 10%/7% plan is ~1.4–1.6x, 2.0 would starve the pipeline).
- **Current honest numbers (deduped, 10 signals):** win rate 20% (2W/2L/6H), expectancy −3.60%, PF 0.78. Calibration: 60-69 bucket 33% win → calibrated 33%; 70-79 (4 sigs) 0% → 30% floor. Auto-execute remains gated off.
- Known cosmetic quirk (not fixed): calibration report buckets floor at 60 (50-conf signals land in "60-69") while `show_results` buckets by decile — pre-existing, display-only.

### Caveat
- Calibration and backtest results now dedupe same-ticker/same-day signals (Session 10 follow-up #2); raw outcome rows still exist in the DB but aggregates use the deduped set (16 → 10).
- 11/16 raw (6/10 deduped) outcomes are HOLD (never hit target or stop within horizon) — win rate counts them as non-wins.

### Suggested next steps (continue here)
1. Wire Session-8 backtest winners (price-only spikes, defence/railways) into the live screener as filters.
2. Consider deduping same-ticker outcomes before calibration.
3. Keep accumulating outcomes (auto-resolve now runs with every `run`/`scan`).

---

## Session 9 (2026-08-02) — Company-less Catalyst News → Research-Based Beneficiary Discovery

### What we did
1. ✅ **Handled "company-less" catalyst news** (e.g., "₹12cr missile order", "Rs 50,000 cr defence export target") — articles with money + decision but NO named company. Previously killed by the pre-filter.
   - Check 5 pre-filter (`pipeline.py` `_MONEY_RE` + `_has_decision_keyword`): passes money+decision generic articles into triage (stats `generic_money_decision`).
   - **Stage 1.5 research** (`_research_catalyst`): free Google/Bing News RSS via new `src/research/searcher.py` (`research_news()`); no API key. Short keyword queries (`_key_tokens`, max 5 tokens) — long sentences return 0 results.
   - Entity extraction now sees `KNOWN_SECTOR_COMPANIES` (candidates from sector map, `_build_sector_candidates`) + research findings; `ENTITY_PROMPT` extended.
   - **Implied beneficiary**: when no company is named, the chosen company is flagged `implied_beneficiary=True`, confidence ×0.85 (floor 55), printed as "🔎 Implied beneficiary: company NOT named in news (inferred via research)". Research may surface NEW companies not in the universe; only NSE/BSE-tradeable ones pass on-the-fly validation.
   - New config: `config/settings.yaml` → `research:` (enabled, max_results 8, freshness 7d, timeout 8s), `tokens.research: 700`; `config/providers.yaml` → `research` task route (groq llama-3.3-70b, max_tokens 700, temp 0.1); `src/config.py::get_research_config()`.

2. ✅ **Fixed LLM name/ticker confusion** (3 bugs over 3 full runs):
   - Run 1: "Zen Technologies Ltd" resolved to Zensar (ZENSARTECH.BO) → added `_name_matches` token guard in `src/universe/builder.py::_search_ticker_by_name`.
   - Run 2: "Zen Tech [WAAREE.BO]" (Waaree Technologies = solar/glass) slipped through → guard added in `_analyze_impact`.
   - Runs 2/3: the guard's remap branch **blindly trusted `resolve_ticker`**, which fuzzy-matches "MTAR Technologies" → TATATECH.NS and "Zen Technologies Limited" → WAAREE.BO (shared "Technologies Limited") → it "remapped" to the SAME wrong ticker. **Fix**: new `_reconcile_name_ticker()` helper — a ticker is accepted only if the pred name matches the stock name OR the ticker base (with `_norm_name` normalization: ltd→limited, punctuation); an alternate is tried only if ITS name/base matches too; else DISCARDED. Unit-tested (11 cases) + verified end-to-end in run 3.
   - Also fixed a main.py `for-else` misprint ("No qualifying signals found today" printed even when signals existed).

3. ✅ **3 full runs** (each ~11–13 min, 40–72 LLM calls, 38–128k est tokens): pipeline works end-to-end; the daily LLM budget (300 calls / 120k tokens, persisted in `data/daily_llm_stats.json`) resets per-day (deleting the file resets it manually).
4. ✅ **Signal output shows what a found company is related to**: signal dict now includes `stock.sector_display` (readable label, prefers catalyst `product_category` via `_CATEGORY_TO_SECTOR`, falls back to stock sector), top-level `relation` (from impact pred `reasoning` — the specific link, e.g. "provides hardware for missile systems..."), and `stock.newly_added` (ticker not in base universe → on-the-fly added). `main.py` prints a "🏭 Sector: ... | ..." line + "🆕 Newly discovered company" marker. TradePlan gained a `relation` field; pipeline tracks `_base_universe` in `__init__`. Note: impact prompt field `catalyst_to_relevity` (LLM fills it with HQ city) is aliased to `catalyst_to_revenue` — misleading but unused downstream.

### Current state
- Universe 58 stocks (cached). Dynamic additions OK (e.g., APOLLO.BO → APOLLO.NS). Defence small-caps (ZENTEC, ASTRAMICRO, PARASDEF, DATAPATTNS, MAZDOCK, BRAHMOS) mostly fail Yahoo validation → genuinely untradeable, correctly discarded.
- Run 3 output: Apollo Micro [APOLLO.NS], Dev IT [DEVIT.NS], ideaForge [IDEAFORGE.NS] — all WATCH, implied beneficiary, calibrated 50–55%, no auto-execute.

### Caveat
- Implied-beneficiary signals are speculative (e.g., ideaForge inferred from a BrahMos-missiles article); they are flagged + confidence-penalized, but the LLM inference can be a stretch. Research narrows the company but does not guarantee it actually benefits.

### Suggested next steps (continue here)
1. Commit/push Session 8+9 changes (ask user first — still uncommitted).
2. Let signals accumulate to measure real accuracy (DB still has 0 resolved outcomes).
3. Wire Session-8 backtest winners (price-only spikes, defence/railways) into the live screener.

---

## Session 8 (2026-08-01) — Universe Expansion + Historical Accuracy Backtest

### What we did
1. ✅ **Expanded the universe 45 → 58 stocks** (`src/universe/builder.py`):
   - `build()` now merges candidates from Screener.in + sector reference tickers + **NSE/BSE lookup JSON + `TICKER_ALIASES`** (new `_get_lookup_tickers()` method).
   - Widened Screener.in queries to match loosened filters (price 20–1000, cap 50–50k Cr).
   - **Important**: Screener.in custom screens now require LOGIN → `_discover_from_screener()` returns 0 rows. Discovery relies on lookup/sector pool only.
   - ~50% of lookup tickers (newly-listed small-caps like WAAREE, TASL, PARASDEF, APOLLOMICRO, TEXMACO, VRL) have **NO Yahoo data** (verified: both `info` and `history` return nothing) → they can never be validated/added. Genuine data-source limitation.
   - Filters loosened earlier in `config/settings.yaml`: price 20–1000, cap 50–50,000Cr, vol 10L, value 0.5Cr, age 90d.

2. ✅ **Built `scripts/historical_backtest.py`** — replays the spike-scan trigger (`screener.py:scan_price_volume_spikes`) over 2–3 years of daily OHLCV across the universe. Entry = next-day open, stop-first exits, cooldown. 17 parameter configs, breakdowns by sector / spike-type / cap bucket / year. Results → `data/historical_backtest.json`. Price data cached in `data/price_history/`.

### KEY FINDING — the mechanical spike trigger alone is NOT profitable
- **~57,000 simulated trades**, 17 configs, 2y + 3y runs (consistent):
  - Closed-trade win rate: 23–36% (median ~29%); breakeven at 2:1 RR needs ~33%
  - Expectancy: −0.07R to +0.04R (median −0.02R); only 4/17 configs marginally +EV
  - Profit factor < 1 everywhere (0.5–0.94)
- Sub-edges that survive (worth wiring into pipeline as filters):
  - **Price-only spikes** (drop volume-only): +0.02–0.06R, PF ~0.87–0.94
  - **Defence/Railways/Manufacturing sectors**: +0.04R, PF 0.94 (config `defence_railways`)
  - Volume-only spikes worst (−0.13R). Edge decayed over time (2023 +0.07R → 2025 −0.06R).
- Optimistic vs conservative exit convention changes nothing → result is robust.

### Caveat to remember
The price backtest measures ONLY the mechanical screen. The live bot's news + LLM confirmation layer is NOT covered. Real accuracy can only be measured via resolved outcomes (`python main.py backtest`) — **DB still has 0 outcomes** (18 articles, 4 signals). This is the honest gap.

### Current uncommitted work-in-progress
Working tree has uncommitted changes (pre-session) across:
`config/nse_bse_tickers.json`, `config/sectors.yaml`, `config/settings.yaml`, `src/analysis/pipeline.py`, `src/universe/builder.py`, `src/universe/ticker_map.py`
(plus this session's new `scripts/historical_backtest.py` + `data/historical_backtest.json`).
NOT committed/pushed. Ask user before committing.

### Questions user asked (answered, may want follow-up)
- "Will a news company not in the universe be rejected?" → No, if real + tradable: on-the-fly validation (known map → yfinance NS/BO → name search → NSE/BSE lookup) adds it live. Rejected only if no Yahoo data OR fails safety filter (pipeline.py:378-415).
- "What is the universe used for?" → Watchlist for spike-scanning, article→ticker matching pool, price/sector source for signals. Not a hard gate (dynamic additions allowed).

### Suggested next steps (continue here)
1. Wire the winning filters into the live pipeline (price-only spikes, defence/railways sectors).
2. Optionally fix Screener.in discovery (login-based scraping or API).
3. Accumulate real outcomes to measure the LLM/news layer accuracy.
4. Commit/push current changes (ask user first).

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
- **Branch**: main
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
- ✅ Groq (8 keys) — main AI provider
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

### Session 11 — Manual holdings tracker + reminders + budget scale-up
- `src/portfolio/bot.py` — **NEW** — Telegram long-polling, inline button callbacks, pending-input state machine, `run_reminder_check()`, `_send_holdings_list`, `fetch_current_price()`
- `src/portfolio/telegram.py` — `reply_markup` support, `make_inline_keyboard`, `answer_callback_query`, `edit_message_reply_markup`, signal buy/skip buttons
- `src/storage/db.py` — `holdings` table + full CRUD (`store_holding`, `mark_holding_sold`, `extend_holding`, `mark_holding_reminded`, `reset_holdings_nudges`, …), holdings in stats
- `src/config.py` — `get_holdings_config()`; `config/settings.yaml` — `holdings:` block + `llm_budget:` raised (1.5M tokens / 1500 calls)
- `main.py` — `scheduled_reminders()` + `bot_poll_loop()` scheduler jobs, `holds` command, async `run_scheduler` fix, CronTrigger `minute="0,30"` fix

### Session 10 follow-up — screener winners + dedupe + R:R config
- `src/screening/screener.py` — `scan_price_volume_spikes` Session-8 edge ranking (both > price > volume, priority sectors, volume-only cap), `ScreenerCandidate.sector`/`spike_type`
- `src/storage/db.py` — `get_all_outcomes(dedupe=True)` + `get_outcomes_for_calibration()` dedupe by (ticker, day) via `_dedupe_by_ticker_day`
- `src/config.py` — `get_screening_config()`; `config/settings.yaml` — `screening:` block, `signals.min_risk_reward_ratio: 1.5`
- `src/analysis/pipeline.py` — `_validate_trade_plan` reads `min_risk_reward_ratio` from config
- `main.py` — passes `universe` to spike scan; `scripts/backtest.py` — shows dedupe collapse count

### Session 10 — Trade-plan validation + outcome resolution + auto-resolve
- `src/analysis/pipeline.py` — `_parse_price()`, `_GARBAGE_THESIS`, `_NON_STOCK_ENTITIES`, `_validate_trade_plan()` (inverted/degenerate plan rejection, honest R:R ≥1.5, thesis guard, level normalisation), `_signal_in_cooldown()` (48h per-ticker), non-stock entity guard in `_analyze_impact`, validation wired into `_create_trade`
- `main.py` — `auto_resolve_outcomes()` called at start of `run_pipeline` and `run_screener_pipeline` (resolve + recalibrate, best-effort)
- `scripts/backtest.py` — `resolve_outcomes()` gains `min_age_days=1` (skips same-day signals, no wasted yfinance call)
- `SESSION_MEMORY.md` — Session 10 section (this)

### Session 9 — Company-less catalysts + research + name/ticker guard
- `src/research/searcher.py`, `src/research/__init__.py` — **NEW** — `research_news()` via Google/Bing News RSS (no API key)
- `src/ai/prompts.py` — RESEARCH system/prompt, `build_research_prompt()`, `format_research_results()`; QUICK_FILTER + TRIAGE accept company-less money+decision news; ENTITY_PROMPT gains candidates + research grounding
- `src/analysis/pipeline.py` — Check 5 pre-filter, `_research_catalyst()` (Stage 1.5), `_build_sector_candidates()`, `_key_tokens()`/`_build_research_query()`, `_is_implied_beneficiary()`, `implied_beneficiary` fields, `_reconcile_name_ticker()` + `_norm_name()` (name/ticker guard), `_MONEY_RE`/`_DECISION_KEYWORDS`
- `src/universe/builder.py` — `_name_matches`/`_name_tokens`/`_NAME_STOP_TOKENS` guard in `_search_ticker_by_name`
- `src/config.py` — `get_research_config()`; `config/settings.yaml` — `research:` block + `tokens.research`; `config/providers.yaml` — `research` task route
- `main.py` — "🔎 Implied beneficiary" print (run + screener), "🏭 Sector | relation" + "🆕 Newly discovered" prints, fixed `for-else` no-signals misprint

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
