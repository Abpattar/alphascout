"""
AI Prompt Templates for AlphaScout Pipeline
4-Stage: Triage → Entity Extraction → Impact Analysis → Trade Setup
"""

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1: TRIAGE - Catalyst Detection & Classification
# ─────────────────────────────────────────────────────────────────────────────

TRIAGE_SYSTEM = """You are an expert Indian stock market analyst specializing in SMALL/MID CAP companies (<₹5000 Cr market cap).
Identify if news contains a TRADEABLE CATALYST that will move stock prices in 3-7 days.

IMPORTANT: Flag potential pump-and-dump or corporate PR risks. Watch for:
- Promotional language ("multibagger", "next 10x", "once in a lifetime")
- Company's own press release without independent corroboration
- Timing suspiciously close to a recent price run-up
- Lack of specific financial details (no ₹ values, no timelines)
- Generic "expansion plans" or "strategic vision" without concrete orders

CRITICAL PR/PUMP RULE (Problem 7):
- If the ONLY source is the company's own press release/website, flag pr_pump_risk as HIGH
- If no independent news outlet has confirmed the news, flag pr_pump_risk as HIGH
- A signal should NEVER be generated from company PR alone — require at least one independent source
- "Strategic partnership" or "MoU signed" without specific ₹ values = HIGH PR risk
- Vague "expansion plans" without concrete order numbers = HIGH PR risk

RETURN ONLY VALID JSON. No markdown, no explanation."""

TRIAGE_PROMPT = """Analyze this news article for tradeable catalysts:

TITLE: {title}
CONTENT: {content}
SOURCE: {source}

Catalyst Types:
- ORDER: New contract/order announced (₹ value if mentioned)
- EXPORT: Export deal/foreign order
- EARNINGS: Quarterly results beat/miss, guidance change
- POLICY: Government policy, PLI scheme, budget allocation, regulation
- GEOPOLITICAL: Border tension, defense spending, strategic developments
- PARTNERSHIP: JV, technology transfer, strategic alliance
- CAPACITY: New plant, expansion, capex announcement
- MANAGEMENT: Promoter buying, insider activity, key hire

Time Sensitivity:
- IMMEDIATE: Contract signed TODAY, specific order announced NOW (1-7 days impact)
- SHORT: Deal finalized, earnings declared (1-3 weeks)
- MEDIUM: Policy announced, budget allocated (2-4 weeks)
- LONG: Strategic plans, MoU signed (1-3 months)

Return JSON:
{{
  "has_catalyst": true/false,
  "catalyst_type": "ORDER/EXPORT/EARNINGS/POLICY/GEOPOLITICAL/PARTNERSHIP/CAPACITY/MANAGEMENT/OTHER",
  "time_sensitivity": "IMMEDIATE/SHORT/MEDIUM/LONG",
  "event_summary": "One clear sentence: what happened, who, how much",
  "money_involved": "₹X crore or null",
  "product_category": "defence/railways/ev/renewable/infra/manufacturing/chemicals/pharma/it/other",
  "named_companies": ["explicit company names mentioned"],
  "implied_companies": ["likely beneficiaries not explicitly named"],
  "catalyst_strength": "STRONG/MODERATE/WEAK",
  "key_quote": "Most impactful sentence from article (max 200 chars)",
  "pr_pump_risk": "LOW/MEDIUM/HIGH",
  "pr_pump_flags": ["specific red flags found, e.g. 'promotional language', 'no independent source', 'company PR only'"],
  "independent_sources_count": 0,
  "source_tier_note": "Tier 1=govt/regulatory (highest), Tier 2=mainstream, Tier 3=niche, Tier 4=corporate PR (lowest)"
}}

FILTER OUT:
- Non-business news (politics, sports, entertainment)
- Vague "sector outlook" without specific company mention
- Pure market commentary with no specific stock mentioned"""


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2: ENTITY EXTRACTION - Companies, Tickers, Financial Details
# ─────────────────────────────────────────────────────────────────────────────

ENTITY_SYSTEM = """You are a financial entity extraction specialist for Indian markets.
Extract ALL companies, tickers, financial figures, and products from news.
Focus on SMALL/MID CAP companies (<₹5000 Cr market cap) that can move 10%+ in a week.

RETURN ONLY VALID JSON."""

ENTITY_PROMPT = """Extract structured entities from this catalyst event:

EVENT: {event_summary}
TYPE: {catalyst_type}
MONEY: {money_involved}
PRODUCT: {product_category}
NAMED: {named_companies}
SOURCE: {source}
FULL_CONTENT: {content}

Return JSON:
{{
  "companies": [
    {{
      "name": "Exact company name",
      "ticker": "NSE ticker with .NS (e.g., DATAPATTNS.NS) or null if unknown",
      "market_cap_category": "MICRO/SMALL/MID/LARGE",
      "role": "DIRECT_BENEFICIARY/SUPPLIER/HIDDEN_PLAY/ECOSYSTEM",
      "reason": "Why this company benefits from THIS specific event",
      "mentioned_explicitly": true/false,
      "confidence": 70-95
    }}
  ],
  "financial_details": {{
    "order_value_cr": number or null,
    "contract_duration_years": number or null,
    "margin_hint": "text or null",
    "execution_timeline": "text or null"
  }},
  "products_mentioned": ["product1", "product2"],
  "competitors_mentioned": ["comp1", "comp2"],
  "supply_chain_hints": ["upstream/downstream company or product"]
}}

PRIORITIZE small/mid caps that are:
- Direct suppliers to the named company
- Niche component manufacturers
- Testing/certification labs
- Software/simulation for the sector
- Raw material suppliers

EXCLUDE: Nifty 50, Sensex 30 unless they have a DIRECTLY named specific order/deal with ₹ value. Prefer small/mid caps for higher move potential."""


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3: IMPACT ANALYSIS - Direction, Magnitude, Confidence
# ─────────────────────────────────────────────────────────────────────────────

IMPACT_SYSTEM = """You are a quant analyst predicting SMALL/MID CAP stock price impact from news catalysts.
Focus on 3-7 day price movement for companies <₹500 share price.
Be SPECIFIC with percentages and reasoning.

RETURN ONLY VALID JSON."""

IMPACT_PROMPT = """Predict price impact for each company from this catalyst:

EVENT: {event_summary}
TYPE: {catalyst_type}
MONEY: {money_involved}
PRODUCT: {product_category}
TIMEFRAME: {time_sensitivity}
STRENGTH: {catalyst_strength}

COMPANIES:
{companies_json}

For EACH company, predict:
- Direction: UP/DOWN/NEUTRAL
- Expected % move in 3-7 days
- Confidence (60-95%)
- Key reasoning (max 2 sentences)
- Risk factors (1-2)
- Whether technical setup supports the move

Return JSON:
{{
  "predictions": [
    {{
      "ticker": "EXACT.NS",
      "name": "Company Name",
      "direction": "UP/DOWN/NEUTRAL",
      "expected_move_pct": 8-25,
      "confidence": 65-95,
      "reasoning": "Specific reason linking THIS event to THIS company's revenue/orders",
      "key_risk": "What could invalidate this thesis",
      "technical_support": "above 20DMA / RSI < 70 / volume spike / breakout / neutral",
      "supply_chain_tier": "TIER1/TIER2/TIER3",
      "catalyst_to_relevity": "Headquarters city (for regional bias check)"
    }}
  ],
  "sector_impact": "POSITIVE/NEGATIVE/NEUTRAL for {product_category} sector",
  "market_regime_note": "Bullish/Bearish/Neutral - broader market context"
}}

CRITICAL: Only predict UP if catalyst is POSITIVE for revenue/orders.
Predict DOWN for: order cancellation, penalty, ban, competitor win, raw material cost spike.
NEUTRAL if impact unclear or already priced in."""


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4: TRADE SETUP - Entry, Target, Stop, Position Size
# ─────────────────────────────────────────────────────────────────────────────

TRADE_SYSTEM = """You are a professional trader creating EXECUTABLE trade plans for 3-7 day horizon.
Risk management is paramount. Every trade must have defined risk/reward ≥ 2:1.

RETURN ONLY VALID JSON."""

TRADE_PROMPT = """Create a precise trade plan for this prediction:

COMPANY: {name} ({ticker})
DIRECTION: {direction}
EXPECTED_MOVE: {expected_move_pct}%
CONFIDENCE: {confidence}%
REASONING: {reasoning}
CATALYST: {event_summary}
CATALYST_TYPE: {catalyst_type}
CURRENT_PRICE: ~{current_price}

Create trade JSON (keep each field SHORT, max 30 chars per string field):
{{
  "ticker": "EXACT.NS",
  "name": "Company Name",
  "trade_type": "STRONG_BUY/BUY/ACCUMULATE/WATCH",
  "direction": "LONG",
  "entry_strategy": "Max 30 chars: e.g. 'Break above ₹125 with volume'",
  "entry_price_range": "₹X-₹Y",
  "target_price": "₹Z",
  "target_pct": 10-25,
  "stop_loss_price": "₹W",
  "stop_loss_pct": 4-8,
  "risk_reward_ratio": 2.0-4.0,
  "hold_days": 3-7,
  "max_hold_days": 10,
  "confidence": 65-95,
  "position_size_pct": 3,
  "thesis_one_line": "Max 50 chars: stock moves Y% because...",
  "key_trigger": "Max 30 chars",
  "kill_switch": "Max 30 chars",
  "supporting_evidence": ["evidence1", "evidence2"],
  "risks": ["risk1", "risk2"],
  "technical_checklist": {{"above_20dma": true, "rsi_level": "55", "volume_trend": "increasing", "near_support": false, "breakout_pending": true}},
  "catalyst_expiry": "7 days"
}}

RULES: Stop loss ≤ 8%, Target ≥ 2x stop, Entry actionable today/tomorrow, Confidence < 70 → WATCH"""


# ─────────────────────────────────────────────────────────────────────────────
# QUICK FILTER (Groq 8B / Fast model) - Pre-screen articles
# ─────────────────────────────────────────────────────────────────────────────

QUICK_FILTER_SYSTEM = """Rapidly classify if news has ANY tradeable catalyst for small/mid caps.
Return ONLY JSON."""

QUICK_FILTER_PROMPT = """Does this news contain a specific catalyst for small/mid cap stocks?

TITLE: {title}
SNIPPET: {snippet}

Return JSON:
{{
  "relevant": true/false,
  "reason": "why relevant or not (max 50 chars)",
  "likely_sector": "defence/railways/ev/renewable/infra/manufacturing/chemicals/pharma/it/other",
  "urgency": "HIGH/MEDIUM/LOW"
}}"""

# ─────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def format_companies_for_impact(companies: list) -> str:
    """Format company list for impact analysis prompt"""
    lines = []
    for c in companies:
        lines.append(
            f"- {c['name']} ({c.get('ticker', 'NO_TICKER')}) | "
            f"Role: {c['role']} | "
            f"Reason: {c['reason']} | "
            f"Confidence: {c['confidence']}% | "
            f"Explicit: {c['mentioned_explicitly']}"
        )
    return "\n".join(lines)


def build_triage_prompt(article: dict) -> tuple:
    return TRIAGE_SYSTEM, TRIAGE_PROMPT.format(
        title=article.get("title", ""),
        content=article.get("content", "")[:2500],
        source=article.get("source", "")
    )


def build_entity_prompt(triage: dict, article: dict) -> tuple:
    return ENTITY_SYSTEM, ENTITY_PROMPT.format(
        event_summary=triage.get("event_summary", ""),
        catalyst_type=triage.get("catalyst_type", ""),
        money_involved=triage.get("money_involved", "null"),
        product_category=triage.get("product_category", ""),
        named_companies=triage.get("named_companies", []),
        source=article.get("source", ""),
        content=article.get("content", "")[:2000]
    )


def build_impact_prompt(triage: dict, entities: dict) -> tuple:
    companies_json = format_companies_for_impact(entities.get("companies", []))
    return IMPACT_SYSTEM, IMPACT_PROMPT.format(
        event_summary=triage.get("event_summary", ""),
        catalyst_type=triage.get("catalyst_type", ""),
        money_involved=triage.get("money_involved", "null"),
        product_category=triage.get("product_category", ""),
        time_sensitivity=triage.get("time_sensitivity", "MEDIUM"),
        catalyst_strength=triage.get("catalyst_strength", "MODERATE"),
        companies_json=companies_json
    )


def build_trade_prompt(prediction: dict, current_price: float = 0) -> tuple:
    return TRADE_SYSTEM, TRADE_PROMPT.format(
        name=prediction.get("name", ""),
        ticker=prediction.get("ticker", ""),
        direction=prediction.get("direction", ""),
        expected_move_pct=prediction.get("expected_move_pct", 0),
        confidence=prediction.get("confidence", 0),
        reasoning=prediction.get("reasoning", ""),
        event_summary=prediction.get("event_summary", ""),
        catalyst_type=prediction.get("catalyst_type", ""),
        current_price=current_price,
        technical_support=prediction.get("technical_support", "neutral"),
        key_risk=prediction.get("key_risk", "")
    )


def build_quick_filter_prompt(title: str, snippet: str) -> tuple:
    return QUICK_FILTER_SYSTEM, QUICK_FILTER_PROMPT.format(title=title, snippet=snippet)