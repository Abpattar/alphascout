"""
Analysis Pipeline
4-Stage: Quick Filter → Triage → Entity Extraction → Impact Analysis → Trade Setup
Optimized with pre-filtering and parallel execution
"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.ai.providers import get_registry, BudgetExhaustedError
from src.ai.prompts import (
    build_triage_prompt,
    build_entity_prompt,
    build_impact_prompt,
    build_trade_prompt,
    build_quick_filter_prompt,
)
from src.universe.ticker_map import extract_tickers, resolve_ticker, get_mapper

logger = logging.getLogger(__name__)

# Readable labels for universe sector slugs
_SECTOR_LABELS = {
    "defence": "Defence",
    "railways": "Railways",
    "ev": "EV",
    "renewable": "Renewable/Green Energy",
    "infra": "Infrastructure",
    "manufacturing_pli": "Manufacturing (PLI)",
    "chemicals_specialty": "Specialty Chemicals",
    "logistics": "Logistics",
    "consumer": "Consumer",
    "it": "IT/AI",
    "it_services": "IT/AI",
    "software": "IT/AI",
    "ai": "AI",
}

# Catalyst product_category -> sector slug (used for display; the catalyst sector
# is usually a better description of what a newly-found company is related to)
_CATEGORY_TO_SECTOR = {
    "defence": "defence", "defense": "defence", "military": "defence",
    "missile": "defence", "drones": "defence", "drone": "defence",
    "railways": "railways", "rail": "railways",
    "ev": "ev", "electric": "ev", "ev infrastructure": "ev",
    "renewable": "renewable", "solar": "renewable", "green energy": "renewable",
    "infra": "infra", "infrastructure": "infra",
    "manufacturing": "manufacturing_pli", "manufacturing pli": "manufacturing_pli",
    "chemicals": "chemicals_specialty", "chemical": "chemicals_specialty",
    "logistics": "logistics",
    "consumer": "consumer",
    "ai": "it", "it": "it", "software": "it", "technology": "it", "tech": "it",
    "telecom": "it",
}

_NAME_SUFFIX_MAP = {
    "ltd": "limited",
    "corp": "corporation",
    "co": "company",
    "inc": "incorporated",
    "pvt": "private",
    "llc": "limited",
}


def _norm_name(s: str) -> str:
    """Normalize a company name for comparison: lowercase, strip punctuation,
    expand common abbreviations (ltd -> limited)."""
    s = s.lower()
    for a, b in ((".", " "), (",", " "), ("-", " "), ("&", " and "), ("'", "")):
        s = s.replace(a, b)
    words = re.sub(r"\s+", " ", s).strip().split(" ")
    return " ".join(_NAME_SUFFIX_MAP.get(w, w) for w in words if w)


def _reconcile_name_ticker(
    ticker: str,
    pred_name: str,
    universe: Dict[str, Any],
    resolve_fn=resolve_ticker,
) -> Optional[str]:
    """Return the reconciled ticker for a prediction, or None if the
    name/ticker pairing is inconsistent (LLM confusion).

    LLMs sometimes pair a company name with the wrong ticker (e.g. "Zen Tech"
    with WAAREE.BO, or "MTAR Technologies" with TATATECH.NS). A ticker is
    accepted only if the predicted name matches the stock's name OR the
    ticker base. If it matches neither, an alternate is tried and accepted
    only when its own name/base matches in turn; otherwise the prediction
    is rejected.
    """
    if not pred_name:
        return ticker
    if ticker not in universe:
        return None
    stock_name = _norm_name(universe[ticker].name or "")
    pred_lower = _norm_name(pred_name)
    ticker_base = ticker.split(".")[0].lower()
    if pred_lower in stock_name or stock_name in pred_lower:
        return ticker
    if ticker_base in pred_lower or (len(pred_lower) >= 3 and pred_lower in ticker_base):
        return ticker
    alt = resolve_fn(pred_name)
    if alt and alt in universe:
        alt_name = _norm_name(universe[alt].name or "")
        alt_base = alt.split(".")[0].lower()
        if (
            pred_lower in alt_name
            or alt_name in pred_lower
            or alt_base in pred_lower
            or (len(pred_lower) >= 3 and pred_lower in alt_base)
        ):
            return alt
    return None


# ── NSE/BSE real lookup table (Issue 1) ──────────────────────────────────────
_NSE_BSE_LOOKUP: Dict[str, str] = {}
_UNRESOLVED_LOG_PATH = Path(__file__).parent.parent.parent / "data" / "unresolved_candidates.jsonl"

# ── Generic company-less catalyst detection (Check 5) ─────────────────────────
_MONEY_RE = re.compile(
    r'(?:rs\.?|inr|₹)?\s?\d[\d,]*(?:\.\d+)?\s*'
    r'(?:cr|crore|lakh|lacs|million|mn|billion|bn)\b',
    re.IGNORECASE,
)

_DECISION_KEYWORDS = [
    "order", "contract", "tender", "deal", "budget", "allocation", "allocated",
    "policy", "scheme", "subsidy", "capex", "expansion", "acquisition", "merger",
    "investment", "funding", "export", "sanction", "approval", "approved",
    "joint venture", "partnership", "auction", "project", "grant", "missile",
    "defence", "defense", "railway", "railways", "renewable", "electric vehicle",
    "battery", "pharma", "infrastructure", "agreement", "procurement", "mou",
]
_DECISION_KEYWORDS_SHORT = ["ev", "pli", "mod"]


def _has_decision_keyword(text_lower: str) -> bool:
    for kw in _DECISION_KEYWORDS:
        if kw in text_lower:
            return True
    for kw in _DECISION_KEYWORDS_SHORT:
        if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
            return True
    return False


def _load_nse_bse_lookup() -> Dict[str, str]:
    """Load the NSE/BSE company name→ticker lookup from config."""
    global _NSE_BSE_LOOKUP
    if _NSE_BSE_LOOKUP:
        return _NSE_BSE_LOOKUP
    lookup_path = Path(__file__).parent.parent.parent / "config" / "nse_bse_tickers.json"
    try:
        with open(lookup_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _NSE_BSE_LOOKUP = {k.lower(): v for k, v in data.get("lookup", {}).items()}
        logger.info(f"Loaded {len(_NSE_BSE_LOOKUP)} NSE/BSE ticker entries")
    except Exception as e:
        logger.warning(f"Failed to load NSE/BSE ticker lookup: {e}")
        _NSE_BSE_LOOKUP = {}
    return _NSE_BSE_LOOKUP


def _log_unresolved_candidate(article_title: str, extracted_names: List[str], source: str = ""):
    """Append unresolved company names for periodic review."""
    try:
        _UNRESOLVED_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now().isoformat(),
            "title": article_title[:120],
            "names": extracted_names,
            "source": source,
        }
        with open(_UNRESOLVED_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


@dataclass
class TriageResult:
    has_catalyst: bool
    catalyst_type: str
    time_sensitivity: str
    event_summary: str
    money_involved: str
    product_category: str
    named_companies: List[str]
    implied_companies: List[str]
    catalyst_strength: str
    key_quote: str
    pr_pump_risk: str = "LOW"
    pr_pump_flags: List[str] = field(default_factory=list)
    independent_sources_count: int = 0
    source_tier_note: str = ""


@dataclass
class EntityResult:
    companies: List[Dict]
    financial_details: Dict
    products_mentioned: List[str]
    competitors_mentioned: List[str]
    supply_chain_hints: List[str]


@dataclass
class ImpactPrediction:
    ticker: str
    name: str
    direction: str
    expected_move_pct: float
    confidence: int
    reasoning: str
    key_risk: str = ""
    technical_support: str = ""
    supply_chain_tier: str = ""
    catalyst_to_revenue: str = ""
    implied_beneficiary: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "ImpactPrediction":
        # Handle LLM typos and extra fields
        d = dict(d)
        if "catalyst_to_relevity" in d and "catalyst_to_revenue" not in d:
            d["catalyst_to_revenue"] = d.pop("catalyst_to_relevity")
        # Remove unknown keys
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class TradePlan:
    ticker: str
    name: str
    trade_type: str
    direction: str
    entry_strategy: str = ""
    entry_price_range: str = ""
    target_price: str = ""
    target_pct: float = 0.0
    stop_loss_price: str = ""
    stop_loss_pct: float = 0.0
    risk_reward_ratio: float = 0.0
    hold_days: int = 5
    max_hold_days: int = 7
    confidence: int = 0
    position_size_pct: float = 3.0
    thesis_one_line: str = ""
    key_trigger: str = ""
    kill_switch: str = ""
    supporting_evidence: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    technical_checklist: Dict = field(default_factory=dict)
    catalyst_expiry: str = ""
    implied_beneficiary: bool = False
    relation: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "TradePlan":
        d = dict(d)
        # Handle common LLM typos
        typo_map = {
            "supporting_evidence": "supporting_evidence",
            "evidence": "supporting_evidence",
            "kill_criteria": "kill_switch",
            "catalyst_timeline": "catalyst_expiry",
        }
        for wrong, right in typo_map.items():
            if wrong in d and right not in d:
                d[right] = d.pop(wrong)
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {}
        for k, v in d.items():
            if k in valid:
                filtered[k] = v
            elif k in ("ensemble_agreement", "ensemble_size"):
                continue  # skip meta fields
        return cls(**filtered)


class AnalysisPipeline:
    """Orchestrates the 4-stage analysis"""

    def __init__(self):
        self.registry = get_registry()
        self.mapper = get_mapper()
        self._db = None
        self._base_universe = set(self.mapper.universe.keys())

    @property
    def db(self):
        if self._db is None:
            try:
                from src.storage.db import get_db
                self._db = get_db()
            except Exception:
                pass
        return self._db

    def _log_to_db(self, article_id, stage, provider, output, **kwargs):
        """Store LLM analysis to DB (non-fatal)."""
        if self.db and article_id:
            try:
                self.db.store_analysis(article_id, stage, provider, output, **kwargs)
            except Exception as e:
                logger.debug(f"DB store analysis failed: {e}")

    def analyze_article(self, article: Dict) -> Optional[Dict]:
        """Full 4-stage analysis on single article"""
        title = article.get("title", "")[:80]
        logger.info(f"Analyzing: {title}")

        # Store article in DB for traceability
        article_id = None
        if self.db:
            try:
                article_id = self.db.store_article(article)
            except Exception:
                pass

        try:
            # Stage 0: Quick filter
            if not self._quick_filter(article):
                logger.debug(f"REJECTED (quick_filter): {title}")
                return None

            # Stage 1: Triage
            triage = self._triage(article)
            self._log_to_db(article_id, "triage", "ensemble", triage.__dict__ if triage else {},
                            signal_type="none")
            if not triage or not triage.has_catalyst:
                logger.debug(f"REJECTED (no catalyst): {title}")
                return None

            # Skip weak/long-term catalysts
            if triage.catalyst_strength == "WEAK" or triage.time_sensitivity == "LONG":
                logger.debug(f"REJECTED (weak/long): {title} — strength={triage.catalyst_strength}, time={triage.time_sensitivity}")
                return None

            # PR/Pump risk filter (Problem 7: company PR alone should never trigger signal)
            if triage.pr_pump_risk == "HIGH":
                logger.warning(f"REJECTED (high PR/pump risk): {title} — flags: {triage.pr_pump_flags}")
                return None
            if triage.pr_pump_risk == "MEDIUM":
                # Problem 7: If source is tier 3-4 (niche/corporate) AND medium PR risk, reject
                source_tier = getattr(triage, 'source_tier_note', '')
                if 'Tier 4' in source_tier or 'Tier 3' in source_tier:
                    logger.warning(f"REJECTED (medium PR/pump risk from low-tier source): {title}")
                    return None
                logger.info(f"Note: {title} — medium PR/pump risk, will reduce confidence")

            # Stage 1.5: Web research for company-less catalyst news
            research = None
            if not triage.named_companies:
                research = self._research_catalyst(triage, article_id)

            # Stage 2: Entity Extraction
            entities = self._extract_entities(triage, article, research=research, article_id=article_id)
            self._log_to_db(article_id, "entity_extraction", "ensemble",
                            entities.__dict__ if entities else {})
            if not entities or not entities.companies:
                logger.debug(f"REJECTED (no companies): {title}")
                return None

            # Stage 3: Impact Analysis
            predictions = self._analyze_impact(triage, entities)
            self._log_to_db(article_id, "impact_analysis", "ensemble",
                            {"predictions": [p.__dict__ for p in predictions]} if predictions else {})
            if not predictions:
                logger.debug(f"REJECTED (no impact): {title}")
                return None

            # Stage 4: Trade Setup
            trades = []
            for pred in predictions:
                trade = self._create_trade(pred, triage)
                if trade:
                    trades.append(trade)

            if not trades:
                logger.debug(f"REJECTED (no trades): {title}")
                return None

            # Return best trade
            best = max(trades, key=lambda t: t.confidence * t.risk_reward_ratio)
            output = self._format_output(best, triage, article)

            # Store final signal in DB
            if self.db and output:
                try:
                    self.db.store_signal(output, article_id=article_id)
                except Exception as e:
                    logger.debug(f"DB store signal failed: {e}")

            return output

        except BudgetExhaustedError as e:
            logger.warning(f"Budget exhausted during analysis of '{title}': {e}")
            return None
        except Exception as e:
            logger.error(f"Pipeline error for '{title}': {e}")
            return None

    def _quick_filter(self, article: Dict) -> bool:
        """Fast pre-filter using smallest model"""
        system, prompt = build_quick_filter_prompt(
            article.get("title", ""),
            article.get("content", "")[:500]
        )

        result = self.registry.execute_task(
            "quick_filter",
            system,
            prompt,
            max_tokens=200,
            temperature=0.05
        )

        return result and result.get("relevant", False)

    def _triage(self, article: Dict) -> Optional[TriageResult]:
        """Stage 1: Catalyst detection"""
        system, prompt = build_triage_prompt(article)

        result = self.registry.execute_task(
            "triage",
            system,
            prompt,
            max_tokens=500,
            temperature=0.1,
            require_ensemble=False  # Single model for speed
        )

        if not result or not result.get("has_catalyst"):
            return None

        return TriageResult(**result)

    def _research_catalyst(self, triage: TriageResult, article_id=None) -> Optional[dict]:
        """
        Stage 1.5: For company-less catalyst news, search the web and have the
        LLM narrow down which specific companies are involved/benefit.
        Returns {"query", "results", "narrowing"} or None (never raises).
        """
        try:
            from src.research.searcher import research_news
            from src.ai.prompts import build_research_prompt
            from src.config import get_research_config

            cfg = get_research_config()
            if not cfg.get("enabled", True):
                return None

            query = self._build_research_query(triage)
            results = research_news(
                query,
                max_results=int(cfg.get("max_results", 8)),
                freshness_days=int(cfg.get("freshness_days", 7)),
            )
            if not results:
                logger.info(f"Research: no web results for '{query}'")
                return None

            system, prompt = build_research_prompt(triage.__dict__, results)
            narrowing = self.registry.execute_task(
                "research", system, prompt,
                max_tokens=700, temperature=0.1, require_ensemble=False,
            )
            if not narrowing:
                return None

            self._log_to_db(article_id, "research", "ensemble", {
                "query": query,
                "results": [{k: r.get(k) for k in ("title", "link", "source", "published")} for r in results[:6]],
                "narrowing": narrowing,
            })
            return {"query": query, "results": results, "narrowing": narrowing}

        except Exception as e:
            logger.warning(f"Research failed: {e}")
            return None

    def _build_research_query(self, triage: TriageResult) -> str:
        """Build a SHORT keyword query for web search (long sentences get 0 hits)."""
        parts = []
        cat = triage.product_category
        if cat and cat != "other":
            parts.append(cat)
        if triage.money_involved:
            parts.append(triage.money_involved)
        key_tokens = self._key_tokens(triage.event_summary, max_n=5)
        if key_tokens:
            parts.extend(key_tokens)
        text = " ".join(parts)
        return text[:120] or "india defence order"

    @staticmethod
    def _key_tokens(text: str, max_n: int = 5) -> List[str]:
        """Extract meaningful search tokens from a sentence (drop stopwords)."""
        if not text:
            return []
        stop = {
            "the", "a", "an", "of", "to", "in", "for", "by", "with", "on", "is",
            "are", "was", "were", "will", "could", "would", "should", "has", "have",
            "had", "been", "being", "and", "but", "or", "as", "over", "under",
            "its", "their", "it", "this", "that", "these", "those", "from", "at",
            "after", "before", "more", "most", "also", "now", "yet", "new", "only",
            "said", "says", "according", "target", "targets", "drive", "driven",
            "swell", "swelled", "may", "might", "towards", "among", "between",
            "rs", "inr", "cr", "crore", "lakh", "up", "down", "into", "out",
        }
        seen = set()
        out = []
        for tok in re.findall(r"[a-zA-Z]{3,}", (text or "").lower()):
            if tok in stop or tok in seen:
                continue
            seen.add(tok)
            out.append(tok)
            if len(out) >= max_n:
                break
        return out

    def _build_sector_candidates(self, category: str, limit: int = 15) -> str:
        """Known Indian listed companies for this sector — grounds the LLM so it
        names real listed companies instead of hallucinating tickers."""
        from src.config import get_all_sector_tickers
        sector_map = {
            "defence": "defence", "railways": "railways", "ev": "ev",
            "renewable": "renewable", "infra": "infra",
            "manufacturing": "manufacturing_pli", "chemicals": "chemicals_specialty",
            "logistics": "logistics", "consumer": "consumer",
        }
        sector = sector_map.get(category, category)
        all_tickers = get_all_sector_tickers()
        tickers = all_tickers.get(sector, [])
        if not tickers:
            tickers = [t for ts in all_tickers.values() for t in ts]

        names = []
        seen = set()
        for base in tickers:
            if base in seen:
                continue
            seen.add(base)
            nse = f"{base}.NS"
            stock = self.mapper.universe.get(nse) or self.mapper.universe.get(f"{base}.BO")
            names.append(f"{stock.name} ({nse})" if stock else nse)
            if len(names) >= limit:
                break
        return "\n".join(names)

    def _format_research_for_prompt(self, research: dict) -> str:
        if not research:
            return ""
        from src.ai.prompts import format_research_results
        lines = ["WEB SEARCH RESULTS:"]
        lines.append(format_research_results(research["results"]))
        narrowing = research.get("narrowing") or {}
        if narrowing.get("geography_hint"):
            lines.append(f"GEOGRAPHY: money goes to {narrowing['geography_hint']}")
        if narrowing.get("companies_mentioned"):
            mentioned = "; ".join(
                f"{c.get('name', '')} ({c.get('context', '')})" for c in narrowing["companies_mentioned"]
            )
            lines.append(f"COMPANIES MENTIONED IN RESULTS: {mentioned[:600]}")
        if narrowing.get("foreign_beneficiary_only"):
            lines.append("NOTE: beneficiaries appear to be foreign — look for Indian listed suppliers.")
        return "\n".join(lines)

    def _extract_entities(self, triage: TriageResult, article: Dict, research: Optional[dict] = None,
                          article_id=None) -> Optional[EntityResult]:
        """Stage 2: Extract companies and financial details"""
        candidates = self._build_sector_candidates(triage.product_category)
        research_text = self._format_research_for_prompt(research)
        system, prompt = build_entity_prompt(triage.__dict__, article, candidates=candidates, research=research_text)

        result = self.registry.execute_task(
            "entity_extraction",
            system,
            prompt,
            max_tokens=1000,
            temperature=0.1,
            require_ensemble=False  # Single model OK for extraction
        )

        if not result:
            return None

        # Resolve tickers for all companies
        for comp in result.get("companies", []):
            name = comp.get("name", "")
            ticker = comp.get("ticker", "")
            
            # If ticker is wrong or not in universe, try to resolve
            if not ticker or ticker not in self.mapper.universe:
                resolved = resolve_ticker(name)
                if resolved:
                    comp["ticker"] = resolved
                else:
                    # Try fuzzy from text
                    found = extract_tickers(article.get("content", ""))
                    for tk, nm in found.items():
                        if nm.lower() in name.lower() or name.lower() in nm.lower():
                            comp["ticker"] = tk
                            break

        return EntityResult(**result)

    def _analyze_impact(self, triage: TriageResult, entities: EntityResult) -> List[ImpactPrediction]:
        """Stage 3: Predict price impact"""
        system, prompt = build_impact_prompt(triage.__dict__, entities.__dict__)

        result = self.registry.execute_task(
            "impact_analysis",
            system,
            prompt,
            max_tokens=2000,
            temperature=0.15,
            require_ensemble=False  # Single model for speed
        )

        if not result or "predictions" not in result:
            return []

        predictions = []
        for p in result["predictions"]:
            ticker = p.get("ticker", "")
            if not ticker:
                continue

            # Try universe first
            if ticker not in self.mapper.universe:
                # On-the-fly validation for unknown tickers
                from src.universe.builder import validate_ticker_on_the_fly
                company_name = p.get("name", "")
                result_tuple = validate_ticker_on_the_fly(ticker, company_name)
                if result_tuple:
                    actual_ticker, stock = result_tuple
                    logger.info(f"Dynamic: added {actual_ticker} ({stock.name}) to universe")
                    # Update prediction ticker to the actual one found
                    if actual_ticker != ticker:
                        p["ticker"] = actual_ticker
                        ticker = actual_ticker
                else:
                    # Try NSE/BSE lookup table as fallback
                    nse_lookup = _load_nse_bse_lookup()
                    name_lower = company_name.lower()
                    found_via_lookup = False
                    for name_key, lookup_ticker in nse_lookup.items():
                        if len(name_key) < 4:
                            continue
                        if name_key in name_lower or name_lower in name_key:
                            # Try to validate this ticker
                            result_tuple = validate_ticker_on_the_fly(lookup_ticker, company_name)
                            if result_tuple:
                                actual_ticker, stock = result_tuple
                                logger.info(f"NSE/BSE lookup: {company_name} -> {actual_ticker} ({stock.name})")
                                p["ticker"] = actual_ticker
                                ticker = actual_ticker
                                found_via_lookup = True
                                break
                    if not found_via_lookup:
                        logger.warning(f"DISCARDED: {ticker} ({company_name}) — not in universe, failed validation")
                        continue

            stock = self.mapper.universe[ticker]

            # Name/ticker consistency check: LLMs sometimes mix up names and tickers
            # (e.g. name "Zen Tech" paired with ticker WAAREE.BO). When the ticker
            # is already in the universe, no validation happens, so verify manually.
            pred_name = (p.get("name") or "").strip()
            reconciled = _reconcile_name_ticker(ticker, pred_name, self.mapper.universe)
            if reconciled is None:
                logger.warning(
                    f"DISCARDED: {ticker} name/ticker mismatch ('{pred_name}') — LLM confusion"
                )
                continue
            if reconciled != ticker:
                logger.warning(
                    f"Name/ticker mismatch: {ticker} vs '{pred_name}' — remapping to {reconciled}"
                )
                ticker = reconciled
                stock = self.mapper.universe[reconciled]
                p["ticker"] = reconciled

            # Same safety filter as universe build (Problem 3: one filter function everywhere)
            from src.universe.builder import passes_stock_safety_filter
            avg_vol_lakh = stock.avg_volume_lakh if hasattr(stock, 'avg_volume_lakh') else 0
            if not passes_stock_safety_filter(stock.price, stock.market_cap_cr, avg_vol_lakh):
                logger.warning(f"DISCARDED: {ticker} ({stock.name}) — failed safety filter (price=₹{stock.price:.2f}, cap=₹{stock.market_cap_cr:.0f}Cr)")
                continue

            # Soft filter: allow large-caps but penalize confidence
            is_large_cap = stock.market_cap_cr > 5000

            try:
                pred_obj = ImpactPrediction.from_dict(p)
                # Flag + penalize implied beneficiaries (company never named in news)
                implied = self._is_implied_beneficiary(pred_obj.name, entities)
                pred_obj.implied_beneficiary = implied
                if implied:
                    logger.info(
                        f"Implied beneficiary (not named in news): {ticker} ({pred_obj.name}) — "
                        f"confidence penalized"
                    )
                    pred_obj.confidence = max(55, int(pred_obj.confidence * 0.85))
                # Penalize large-caps in ranking (reduce confidence by 15%)
                if is_large_cap:
                    pred_obj.confidence = max(60, int(pred_obj.confidence * 0.85))
                # Penalize medium PR/pump risk (reduce confidence by 20%)
                if triage.pr_pump_risk == "MEDIUM":
                    pred_obj.confidence = max(55, int(pred_obj.confidence * 0.80))
                predictions.append(pred_obj)
            except Exception as e:
                logger.warning(f"Failed to create ImpactPrediction for {ticker}: {e}")

        return predictions

    def _is_implied_beneficiary(self, pred_name: str, entities: EntityResult) -> bool:
        """True if the predicted company was NOT explicitly named in the article."""
        if not pred_name:
            return True
        pred_lower = pred_name.strip().lower()
        for comp in entities.companies:
            name = (comp.get("name") or "").strip().lower()
            if not name:
                continue
            if pred_lower == name or pred_lower in name or name in pred_lower:
                return not bool(comp.get("mentioned_explicitly"))
        return True

    def _create_trade(self, pred: ImpactPrediction, triage: TriageResult) -> Optional[TradePlan]:
        """Stage 4: Create executable trade plan (with circuit history check for Problem 8)"""
        # Get current price from universe (try multiple ticker formats)
        stock = self.mapper.universe.get(pred.ticker)
        if not stock:
            # Try alternate exchange
            base = pred.ticker.replace(".NS", "").replace(".BO", "")
            stock = self.mapper.universe.get(f"{base}.NS") or self.mapper.universe.get(f"{base}.BO")
        if not stock:
            # Try known ticker map
            from src.universe.builder import _KNOWN_TICKER_MAP, validate_ticker_on_the_fly
            normalized = pred.ticker.replace(".NS", "").replace(".BO", "").upper()
            if normalized in _KNOWN_TICKER_MAP:
                mapped = _KNOWN_TICKER_MAP[normalized]
                stock = self.mapper.universe.get(mapped)
            if not stock:
                # Last resort: on-the-fly validation
                result = validate_ticker_on_the_fly(pred.ticker, pred.name)
                if result:
                    actual_ticker, stock = result
                    if actual_ticker != pred.ticker:
                        pred.ticker = actual_ticker

        if not stock:
            logger.warning(f"No stock data for {pred.ticker} ({pred.name}), using AI price")
            current_price = 0
        else:
            current_price = stock.price

        # Problem 8: Check circuit history — recent circuit hits make exit difficult
        from src.universe.builder import check_circuit_history
        circuit_info = check_circuit_history(pred.ticker, days=30)
        if circuit_info["has_circuit_hits"] and circuit_info["circuit_days"] >= 2:
            logger.warning(
                f"CIRCUIT RISK: {pred.ticker} hit circuit {circuit_info['circuit_days']} times in 30 days "
                f"(max lower: {circuit_info['max_lower_circuit_pct']}%) — penalizing confidence"
            )
            # Reduce confidence based on circuit frequency
            circuit_penalty = min(30, circuit_info["circuit_days"] * 10)
            pred.confidence = max(50, pred.confidence - circuit_penalty)

        system, prompt = build_trade_prompt(pred.__dict__, current_price)

        result = self.registry.execute_task(
            "trade_setup",
            system,
            prompt,
            max_tokens=4000,
            temperature=0.2,
            require_ensemble=False
        )

        if not result:
            # Retry with NVIDIA NIM if Groq fails
            try:
                from src.ai.providers import NVIDIANIMProvider
                nim = self.registry.providers.get("nvidia_nim")
                if nim:
                    result = nim.generate(prompt, system, 4000, 0.2)
            except Exception:
                pass

        if not result:
            return None

        # Validate trade quality (relaxed)
        rr = result.get("risk_reward_ratio", 0)
        if rr and rr < 1.5:
            logger.debug(f"R:R too low: {rr}")
            return None

        sl = result.get("stop_loss_pct", 100)
        if sl and sl > 15:
            logger.debug(f"Stop loss too wide: {sl}")
            return None

        try:
            trade = TradePlan.from_dict(result)
            trade.implied_beneficiary = pred.implied_beneficiary
            trade.relation = (pred.reasoning or pred.catalyst_to_revenue or "").strip()
            return trade
        except Exception as e:
            logger.debug(f"Failed to create TradePlan: {e}")
            return None

    def _format_output(self, trade: TradePlan, triage: TriageResult, article: Dict) -> Dict:
        """Format final output with calibrated confidence"""
        stock = self.mapper.universe.get(trade.ticker)

        # Get calibrated confidence
        try:
            from src.analysis.calibration import get_calibrator
            calibrator = get_calibrator()
            raw_conf = trade.confidence
            calibrated_conf = calibrator.get_calibrated(raw_conf)
            should_auto, auto_reason = calibrator.should_auto_execute(raw_conf)[:2]
        except Exception:
            calibrated_conf = trade.confidence
            should_auto = trade.confidence >= 90
            auto_reason = "raw confidence threshold"

        # Display sector: prefer the catalyst-derived sector (what the company is
        # related to), fall back to the stock's own assigned sector.
        catalyst_sector = _CATEGORY_TO_SECTOR.get((triage.product_category or "").lower())
        stock_label = (_SECTOR_LABELS.get(stock.sector, stock.sector.title()) if stock else "Unknown")
        sector_display = _SECTOR_LABELS.get(catalyst_sector, "") or stock_label

        return {
            "signal_id": f"{trade.ticker}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "article": {
                "title": article.get("title"),
                "source": article.get("source"),
                "url": article.get("url"),
                "summary": triage.event_summary
            },
            "catalyst": {
                "type": triage.catalyst_type,
                "time_sensitivity": triage.time_sensitivity,
                "strength": triage.catalyst_strength,
                "money_involved": triage.money_involved,
                "product_category": triage.product_category
            },
            "stock": {
                "name": stock.name if stock else trade.name,
                "sector": stock.sector if stock else "unknown",
                "sector_display": sector_display,
                "exchange": stock.exchange if stock else "unknown",
                "market_cap_cr": stock.market_cap_cr if stock else 0,
                "price": stock.price if stock else 0,
                "newly_added": bool(stock and trade.ticker not in self._base_universe),
            },
            "trade": asdict(trade),
            "calibrated_confidence": calibrated_conf,
            "auto_execute": should_auto,
            "auto_execute_reason": auto_reason,
            "implied_beneficiary": trade.implied_beneficiary,
            "relation": trade.relation,
            "ensemble_agreement": trade.__dict__.get("ensemble_agreement", False)
        }

    def analyze_batch(self, articles: List[any], max_signals: int = 5) -> List[Dict]:
        """Analyze multiple articles, return top signals with pre-filtering.

        Issue 1: Pre-filter now uses the real NSE/BSE ticker lookup table
        (config/nse_bse_tickers.json) instead of regex pattern matching.
        Articles pass if they mention:
          (a) a ticker already in the live universe, OR
          (b) a known company name/alias from the lookup table, OR
          (c) a small-cap keyword (fallback to catch new companies), OR
          (d) any company name that looks like it could be a listed stock.
        """
        nse_lookup = _load_nse_bse_lookup()
        small_cap_keywords = [
            'small cap', 'mid cap', 'micro cap', 'small-cap', 'mid-cap',
            'multibagger', 'penny stock', 'small cap stock', 'mid cap stock',
        ]

        filtered_articles = []

        for article in articles:
            try:
                if hasattr(article, 'to_dict'):
                    article_dict = article.to_dict()
                elif isinstance(article, dict):
                    article_dict = article
                else:
                    continue

                text = f"{article_dict.get('title', '')} {article_dict.get('content', '')[:1000]}"
                text_lower = text.lower()

                # Check 1: Universe tickers (fast path via ticker_map)
                found_tickers = extract_tickers(text)

                # Check 2: Real NSE/BSE company name/alias lookup
                matched_nse_names: List[str] = []
                for name_key, ticker in nse_lookup.items():
                    if len(name_key) < 4:
                        continue
                    if name_key in text_lower:
                        matched_nse_names.append(f"{name_key} -> {ticker}")

                has_nse_match = len(matched_nse_names) > 0

                # Check 3: Small-cap keywords (catch-all for unknown companies)
                has_small_cap_kw = any(kw in text_lower for kw in small_cap_keywords)

                # Check 4: Any company-like name (relaxed filter for auto-discovery)
                has_company_name = False
                if not found_tickers and not has_nse_match and not has_small_cap_kw:
                    # Look for company names that could be listed stocks
                    company_patterns = [
                        r'(?:shares? of|stock of|stock in)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})',
                        r'([A-Z][A-Za-z]+(?:\s+(?:Ltd|Limited|Industries|Systems|Technologies|Defence|Aerospace|Engineering|Power|Motors|Chemicals|Pharma|Infra|Energy)))\b',
                    ]
                    for pattern in company_patterns:
                        matches = re.findall(pattern, article_dict.get('title', '') + ' ' + article_dict.get('content', '')[:500])
                        if matches:
                            has_company_name = True
                            break

                # Check 5: Money + impactful decision (company-less catalyst news,
                # e.g. "Govt allocates ₹120 crore for missiles" with no company named)
                has_generic_catalyst = False
                if not found_tickers and not has_nse_match:
                    if _MONEY_RE.search(text) and _has_decision_keyword(text_lower):
                        has_generic_catalyst = True

                if found_tickers or has_nse_match or has_small_cap_kw or has_company_name or has_generic_catalyst:
                    article_dict['_matched_tickers'] = found_tickers
                    article_dict['_matched_nse_names'] = matched_nse_names
                    article_dict['_has_small_cap_keyword'] = has_small_cap_kw
                    article_dict['_has_company_name'] = has_company_name
                    article_dict['_has_generic_catalyst'] = has_generic_catalyst
                    filtered_articles.append(article_dict)

            except Exception as e:
                logger.warning(f"Pre-filter failed for article: {e}")

        logger.info(
            f"Pre-filtered: {len(filtered_articles)}/{len(articles)} articles "
            f"(universe tickers: {sum(1 for a in filtered_articles if a.get('_matched_tickers'))}, "
            f"NSE/BSE lookup: {sum(1 for a in filtered_articles if a.get('_matched_nse_names'))}, "
            f"small-cap keywords: {sum(1 for a in filtered_articles if a.get('_has_small_cap_keyword'))}, "
            f"company names: {sum(1 for a in filtered_articles if a.get('_has_company_name'))}, "
            f"generic money+decision: {sum(1 for a in filtered_articles if a.get('_has_generic_catalyst'))})"
        )

        if not filtered_articles:
            logger.warning("No articles passed pre-filter")
            return []

        # Process articles in parallel
        signals = []
        failed = 0
        budget_hit = False
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_article = {
                executor.submit(self.analyze_article, article): article 
                for article in filtered_articles[:max_signals * 3]  # Process 3x to account for failures
            }

            for future in as_completed(future_to_article):
                try:
                    result = future.result(timeout=90)  # 90s timeout per article
                    if result:
                        signals.append(result)
                        if len(signals) >= max_signals:
                            break
                    else:
                        failed += 1
                except BudgetExhaustedError:
                    budget_hit = True
                    logger.warning("Budget exhausted in batch — returning partial results")
                    break
                except Exception as e:
                    failed += 1
                    logger.warning(f"Analysis failed: {e}")

        if budget_hit:
            logger.info(f"Pipeline stopped early (budget): {len(signals)} signals collected")
        logger.info(f"Pipeline complete: {len(signals)} signals from {len(filtered_articles)} articles ({failed} failed)")

        # Sort by confidence * R:R
        signals.sort(
            key=lambda s: s["trade"]["confidence"] * s["trade"]["risk_reward_ratio"],
            reverse=True
        )

        # Deduplicate: keep best signal per ticker
        seen_tickers = set()
        unique_signals = []
        for s in signals:
            ticker = s["trade"]["ticker"]
            if ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_signals.append(s)

        return unique_signals[:max_signals]


    def analyze_screener_candidates(
        self,
        candidates: List[Dict],
        articles: List[Dict],
        max_signals: int = 5
    ) -> List[Dict]:
        """
        Screener-first approach:
        1. Take screener candidates (active small-caps)
        2. Find news articles that mention those stocks
        3. Analyze those articles for trade signals
        """
        # Build set of candidate tickers and names for matching
        candidate_tickers = set()
        candidate_names = {}
        for c in candidates:
            ticker = c.get("ticker", "")
            name = c.get("name", "").lower()
            candidate_tickers.add(ticker)
            candidate_names[name] = ticker
            # Also add base ticker (without .NS)
            base = ticker.replace(".NS", "").replace(".BO", "")
            candidate_tickers.add(base)

        logger.info(f"Screener-first: matching {len(candidate_tickers)} tickers against {len(articles)} articles")

        # Find articles that mention any candidate stock
        matched_articles = []
        for article in articles:
            if hasattr(article, 'to_dict'):
                article_dict = article.to_dict()
            elif isinstance(article, dict):
                article_dict = article
            else:
                continue

            text = f"{article_dict.get('title', '')} {article_dict.get('content', '')[:1500]}"
            text_lower = text.lower()

            # Check if article mentions any candidate
            matched_ticker = None
            for ticker in candidate_tickers:
                base = ticker.replace(".NS", "").replace(".BO", "").lower()
                if len(base) >= 4 and base in text_lower:
                    matched_ticker = ticker
                    break

            # Also check company names
            if not matched_ticker:
                for name, ticker in candidate_names.items():
                    if len(name) >= 5 and name in text_lower:
                        matched_ticker = ticker
                        break

            if matched_ticker:
                article_dict['_screener_ticker'] = matched_ticker
                matched_articles.append(article_dict)

        logger.info(f"Screener-first: found {len(matched_articles)} articles matching candidates")

        if not matched_articles:
            # Fallback: try the normal batch analysis
            logger.info("No screener matches, falling back to batch analysis")
            return self.analyze_batch(articles, max_signals)

        # Analyze matched articles
        signals = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_article = {
                executor.submit(self.analyze_article, article): article
                for article in matched_articles[:max_signals * 3]
            }

            for future in as_completed(future_to_article):
                try:
                    result = future.result(timeout=60)
                    if result:
                        signals.append(result)
                        if len(signals) >= max_signals:
                            break
                except Exception as e:
                    logger.error(f"Analysis failed: {e}")

        # Sort by confidence * R:R
        signals.sort(
            key=lambda s: s["trade"]["confidence"] * s["trade"]["risk_reward_ratio"],
            reverse=True
        )

        # Deduplicate
        seen_tickers = set()
        unique_signals = []
        for s in signals:
            ticker = s["trade"]["ticker"]
            if ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_signals.append(s)

        return unique_signals[:max_signals]


# Convenience functions
def analyze_articles(articles: List[Dict], max_signals: int = 5) -> List[Dict]:
    pipeline = AnalysisPipeline()
    return pipeline.analyze_batch(articles, max_signals)


def analyze_with_screener(
    candidates: List[Dict],
    articles: List[Dict],
    max_signals: int = 5
) -> List[Dict]:
    pipeline = AnalysisPipeline()
    return pipeline.analyze_screener_candidates(candidates, articles, max_signals)