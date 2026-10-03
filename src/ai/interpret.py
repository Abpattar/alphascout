"""Prompts for the interpretation stage.

Design rule enforced by every template below: **the model never emits a
market number**. Prices, percentages, indicators and levels are supplied by
code and injected as read-only context; the model is asked only for
classification and prose.

The previous prompts asked for ``entry_price_range``, ``target_price``,
``stop_loss_price``, ``risk_reward_ratio`` and a ``technical_checklist``
containing "above_20dma" and "rsi_level" - none of which the model had data
for. Those fields are gone. The model now returns text and categorical labels
only, and :mod:`src.validation` rejects any numeric key that appears in the
AI block.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

# Event types that can plausibly move an Indian small/mid cap in 3-10 sessions.
MATERIAL_EVENT_TYPES = [
    "ORDER_WIN", "CONTRACT_SIGNED", "EARNINGS_RESULTS", "GUIDANCE",
    "REGULATORY_ACTION", "M_AND_A", "CAPEX_EXPANSION", "FUNDRAISE",
    "MANAGEMENT_CHANGE", "PRODUCT_LAUNCH", "RATING_CHANGE", "DEBT_DEFAULT",
    "CREDIT_EVENT", "INSTITUTIONAL_STAKING", "MACRO_POLICY", "RESEARCH",
    "OTHER",
]

REJECT_REASONS = [
    "NOT_MATERIAL", "SPORTS_OR_CENTRETAINMENT", "NON_BUSINESS",
    "ALREADY_PRICED_IN", "NO_INDIAN_LINKAGE", "OTHER",
]

SYSTEM = """You are an equity research analyst covering Indian listed equities \
(NSE/BSE). You read a news article and assess whether it is material for a \
listed Indian company.

ABSOLUTE RULES - violating any of these makes your output worthless:

1. You MUST NOT output prices, percentages, target prices, stop losses, \
entry prices, risk-reward ratios, moving averages, RSI values, volume figures \
or any other numeric market datum. You are not given that data and you must \
not estimate it. Another system computes all numbers deterministically.
2. You MUST NOT invent company names, ticker symbols or facts not present in \
the article.
3. Only Indian-listed companies (NSE/BSE) are in scope. If the article has no \
demonstrable link to an Indian-listed company, say so.
4. Base every statement on the article text provided. If the article does not \
state something, do not assert it.
5. Keep prose factual and specific. No promotional language, no predictions \
presented as facts.

You return a single JSON object and nothing else."""


def build_assessment_prompt(
    article: Dict[str, Any],
    candidates: Sequence[Dict[str, Any]] = (),
    market_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Prompt for stage 1: is this material, and for whom?

    ``market_context`` carries *real* figures (price, RSI, trend) so the model
    can reason about them, but the JSON schema it must return contains no
    numeric fields - it can only echo a label such as ``trend``.
    """
    title = article.get("title", "")
    body = (article.get("content") or "")[:2500]
    source = article.get("source", "")
    published = article.get("published_at", "")

    candidate_lines = []
    for item in candidates:
        candidate_lines.append(
            f"  - {item.get('company_name')} ({item.get('ticker')}) "
            f"[{item.get('exchange')}] sector={item.get('sector', 'unknown')}"
        )
    candidates_block = "\n".join(candidate_lines) or "  (none matched)"

    context_block = "(no market context available)"
    if market_context:
        price = market_context.get("price")
        kind = market_context.get("price_kind", "unknown")
        rsi = market_context.get("rsi_14")
        trend = market_context.get("trend", "unknown")
        sma = market_context.get("sma_20")
        lines = [
            f"  last traded price : Rs{price} ({kind})",
            f"  trend label       : {trend}",
        ]
        if rsi is not None:
            lines.append(f"  RSI(14)           : {rsi:.1f}")
        if sma is not None:
            lines.append(f"  20-day moving avg : Rs{sma:.2f}")
        context_block = "\n".join(lines)

    return f"""Assess this news article for Indian equity relevance.

ARTICLE SOURCE : {source}
PUBLISHED      : {published}
HEADLINE       : {title}

ARTICLE TEXT:
\"\"\"
{body}
\"\"\"

VERIFIED INDIAN CANDIDATES FOUND IN THIS ARTICLE (tickers are confirmed \
against NSE/BSE listings; use these exact symbols if you reference them):
{candidates_block}

REAL MARKET CONTEXT for the primary candidate (computed from actual price \
history - treat as fact, but do not restate numbers in your JSON):
{context_block}

Return JSON with exactly these keys:

{{
  "is_material": true or false,
  "event_type": one of {json.dumps(MATERIAL_EVENT_TYPES)},
  "direction": "LONG" or "SHORT" or "NEUTRAL",
  "relevance_score": integer 0-100,
  "time_horizon_days": integer 1-30,
  "affected_companies": [
    {{"company_name": "...", "ticker": "...", "role": "DIRECT_BENEFICIARY",
      "reason": "one sentence grounded in the article"}}
  ],
  "why_it_matters": "2-3 sentences on the business impact",
  "key_risk": "one sentence - the main way this thesis fails",
  "catalyst_summary": "one sentence describing the event itself",
  "rejection_reason": null or one of {json.dumps(REJECT_REASONS)}
}}

Guidance:
- relevance_score 80+ means a genuinely material, near-term catalyst for an \
Indian listed company. 50-79 is interesting but weaker. Below 50 is noise.
- Set is_material=false and a rejection_reason when the article is sport, \
entertainment, general commentary, or has no Indian listed company involved.
- affected_companies must use tickers from the verified candidate list above. \
If none fit, return an empty list. Never invent a ticker.
- Do not include any price, target, stop-loss or indicator number anywhere in \
your output."""


def build_research_prompt(company_name: str, event_summary: str) -> str:
    """Prompt for stage 2: qualitative business context.

    Explicitly barred from numbers so this stage cannot reintroduce the
    fabrication problem the first stage avoids.
    """
    return f"""Give a concise business-background note for an analyst.

COMPANY  : {company_name}
EVENT    : {event_summary}

In at most 4 short sentences, describe:
1. What this company does and why the event matters to its business.
2. Whether the effect is likely to show up in revenue, margins, or backlog.
3. The most important thing an analyst should verify before acting.

Do not state any price, valuation multiple, financial figure or percentage. \
Do not speculate beyond what the event implies. No lists."""


def build_signal_narrative_prompt(
    *,
    company_name: str,
    ticker: str,
    event_summary: str,
    why_it_matters: str,
    key_risk: str,
    levels_summary: str,
    technicals_summary: str,
) -> str:
    """Final wording pass. Input already contains verified numbers as text.

    The numbers appear here only so the prose can refer to them in words
    ("a 3.4% stop") without the model having to compute or invent them. The
    schema is strings only.
    """
    return f"""Write the analyst commentary for one trade signal.

COMPANY      : {company_name} ({ticker})
EVENT        : {event_summary}
WHY IT MATTERS: {why_it_matters}
KEY RISK     : {key_risk}

VERIFIED NUMERICS (already computed by code - quote them only if natural, and \
never recompute or adjust them):
{levels_summary}

VERIFIED TECHNICALS (already computed from real price history):
{technicals_summary}

Return JSON with exactly these string keys:

{{
  "thesis": "one sentence, max 160 characters, stating the trade case",
  "watchpoint": "one sentence: the single thing to watch that would confirm \
or kill this",
  "evidence": "one short sentence citing what in the article supports this"
}}

Rules:
- Use only the company, ticker and event given above.
- Do not introduce any number that is not in the verified sections above.
- No hype, no guarantees, no price predictions."""


def build_summary_prompt(count: int, tickers: Sequence[str]) -> str:
    """One-line run summary."""
    joined = ", ".join(tickers) if tickers else "none"
    return (
        f"A news scan produced {count} qualifying signal(s) for: {joined}. "
        "Write a single short sentence summarising the run for a log line. "
        "No numbers beyond those given, no company names beyond those listed."
    )
