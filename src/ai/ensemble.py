"""
Multi-Model Ensemble Orchestrator
Routes tasks to best provider, handles fallbacks, enforces agreement
"""
import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .providers import (
    GroqMultiKeyProvider,
    OpenRouterProvider,
    CerebrasProvider,
    GeminiProvider,
    BaseProvider,
    RateLimitError,
    ProviderError,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    task: str
    provider: str
    model: str
    result: Optional[Dict]
    latency_ms: int
    error: str = ""


class EnsembleOrchestrator:
    """
    Manages multiple AI providers with intelligent routing:
    - Primary model per task type
    - Automatic fallback on rate limits/errors
    - Ensemble agreement for critical decisions
    - Cost/latency optimization
    """

    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.multi_key_providers: Dict[str, Any] = {}
        self._init_providers()

    def _init_providers(self):
        """Initialize all available providers from env"""
        # Groq Multi-Key (Primary for reasoning)
        try:
            self.multi_key_providers["groq_70b"] = GroqMultiKeyProvider("llama-3.3-70b-versatile")
            logger.info(f"✅ Groq 70B: {self.multi_key_providers['groq_70b'].get_stats()['keys']} keys loaded")
        except Exception as e:
            logger.warning(f"Groq 70B init failed: {e}")

        try:
            self.multi_key_providers["groq_8b"] = GroqMultiKeyProvider("llama-3.1-8b-instant")
            logger.info(f"✅ Groq 8B: {self.multi_key_providers['groq_8b'].get_stats()['keys']} keys loaded")
        except Exception as e:
            logger.warning(f"Groq 8B init failed: {e}")

        # OpenRouter (Unlimited free models)
        or_key = os.environ.get("OPENROUTER_API_KEY")
        if or_key:
            self.providers["openrouter_qwen"] = OpenRouterProvider(or_key, "qwen/qwen-2.5-72b-instruct:free")
            self.providers["openrouter_nemotron"] = OpenRouterProvider(or_key, "nvidia/nemotron-3-ultra:free")
            self.providers["openrouter_llama8b"] = OpenRouterProvider(or_key, "meta-llama/llama-3.1-8b-instruct:free")
            logger.info("✅ OpenRouter: 3 models loaded")
        else:
            logger.warning("OpenRouter key not set")

        # Cerebras (Fast)
        cb_key = os.environ.get("CEREBRAS_API_KEY")
        if cb_key:
            try:
                self.providers["cerebras_70b"] = CerebrasProvider(cb_key, "llama3.1-70b")
                self.providers["cerebras_8b"] = CerebrasProvider(cb_key, "llama3.1-8b")
                logger.info("✅ Cerebras: 2 models loaded")
            except Exception as e:
                logger.warning(f"Cerebras init failed: {e}")
        else:
            logger.warning("Cerebras key not set")

        # Gemini (Google)
        gm_key = os.environ.get("GEMINI_API_KEY")
        if gm_key:
            try:
                self.providers["gemini_flash"] = GeminiProvider(gm_key, "gemini-1.5-flash")
                self.providers["gemini_pro"] = GeminiProvider(gm_key, "gemini-1.5-pro")
                logger.info("✅ Gemini: 2 models loaded")
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")
        else:
            logger.warning("Gemini key not set")

    # ─────────────────────────────────────────────────────────────────────────
    # TASK ROUTING
    # ─────────────────────────────────────────────────────────────────────────

    def execute_task(
        self,
        task_type: str,
        system: str,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.1,
        require_ensemble: bool = False,
        ensemble_models: List[str] = None
    ) -> Optional[Dict]:
        """
        Execute a single task with smart routing.
        
        Args:
            task_type: triage, entity_extraction, impact_analysis, trade_setup, quick_filter
            system: System prompt
            prompt: User prompt
            max_tokens: Max tokens
            temperature: Temperature
            require_ensemble: If True, run on multiple models and require agreement
            ensemble_models: Specific models to use for ensemble
        """
        if require_ensemble:
            return self._execute_ensemble(
                task_type, system, prompt, max_tokens, temperature, ensemble_models
            )

        # Single model execution with fallback chain
        return self._execute_with_fallback(task_type, system, prompt, max_tokens, temperature)

    def _execute_with_fallback(
        self,
        task_type: str,
        system: str,
        prompt: str,
        max_tokens: int,
        temperature: float
    ) -> Optional[Dict]:
        """Execute with provider fallback chain"""

        # Define routing per task type
        routing = self._get_routing(task_type)

        for provider_name in routing:
            provider = self._get_provider(provider_name)
            if not provider:
                continue

            try:
                start = time.time()
                result = provider.generate(
                    prompt=prompt,
                    system=system,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
                elapsed = int((time.time() - start) * 1000)

                if result:
                    logger.debug(f"✅ {task_type} via {provider_name} ({elapsed}ms)")
                    return result

            except RateLimitError as e:
                logger.warning(f"⚡ Rate limit on {provider_name}: {e}")
                continue
            except ProviderError as e:
                logger.warning(f"⚠️ {provider_name} error: {e}")
                continue
            except Exception as e:
                logger.error(f"❌ {provider_name} unexpected error: {e}")
                continue

        logger.error(f"All providers failed for {task_type}")
        return None

    def _execute_ensemble(
        self,
        task_type: str,
        system: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        ensemble_models: List[str] = None
    ) -> Optional[Dict]:
        """Run on multiple models, require agreement"""

        # Default ensemble models per task
        if not ensemble_models:
            ensemble_models = self._get_ensemble_models(task_type)

        results = []

        # Run in parallel
        with ThreadPoolExecutor(max_workers=len(ensemble_models)) as executor:
            futures = {}
            for model_name in ensemble_models:
                provider = self._get_provider(model_name)
                if provider:
                    futures[executor.submit(
                        self._safe_generate, provider, prompt, system, max_tokens, temperature
                    )] = model_name

            for future in as_completed(futures):
                model_name = futures[future]
                try:
                    result = future.result(timeout=30)
                    if result:
                        results.append({"model": model_name, "result": result})
                except Exception as e:
                    logger.warning(f"Ensemble {model_name} failed: {e}")

        if len(results) < 2:
            logger.warning(f"Ensemble insufficient results: {len(results)}")
            return results[0]["result"] if results else None

        # Check agreement
        agreed = self._check_agreement(results)
        if agreed:
            # Boost confidence
            agreed["ensemble_agreement"] = True
            agreed["agreeing_models"] = len(results)
            agreed["confidence"] = min(agreed.get("confidence", 70) + 10, 95)
            logger.info(f"✅ Ensemble agreement on {task_type}: {len(results)} models")
            return agreed

        logger.warning(f"⚠️ Ensemble disagreement on {task_type}")
        # Return highest confidence result
        return max(results, key=lambda x: x["result"].get("confidence", 0))["result"]

    def _safe_generate(self, provider, prompt, system, max_tokens, temperature):
        """Wrapper for ThreadPoolExecutor"""
        return provider.generate(prompt, system, max_tokens, temperature)

    def _check_agreement(self, results: List[Dict]) -> Optional[Dict]:
        """Check if models agree on key fields"""
        if len(results) < 2:
            return None

        # Compare key fields
        first = results[0]["result"]
        key_fields = ["direction", "ticker", "trade_type"]

        for field in key_fields:
            if field not in first:
                continue
            values = [r["result"].get(field) for r in results]
            if len(set(values)) > 1:
                return None  # Disagreement

        # Check magnitude agreement (within tolerance)
        magnitudes = [r["result"].get("expected_move_pct", 0) for r in results]
        if magnitudes and max(magnitudes) - min(magnitudes) > 5:
            return None  # Too much variance

        return first

    # ─────────────────────────────────────────────────────────────────────────
    # ROUTING CONFIG
    # ─────────────────────────────────────────────────────────────────────────

    def _get_routing(self, task_type: str) -> List[str]:
        """Get provider priority chain for task"""
        routes = {
            "quick_filter": ["groq_8b", "cerebras_8b", "openrouter_llama8b", "gemini_flash"],
            "triage": ["groq_70b", "cerebras_70b", "openrouter_qwen", "gemini_pro"],
            "entity_extraction": ["gemini_flash", "openrouter_llama8b", "cerebras_8b", "groq_8b"],
            "impact_analysis": ["groq_70b", "cerebras_70b", "openrouter_qwen", "gemini_pro"],
            "trade_setup": ["groq_70b", "openrouter_nemotron", "openrouter_qwen", "gemini_pro"],
        }
        return routes.get(task_type, ["groq_70b", "openrouter_qwen"])

    def _get_ensemble_models(self, task_type: str) -> List[str]:
        """Get models for ensemble voting"""
        ensembles = {
            "impact_analysis": ["groq_70b", "cerebras_70b", "openrouter_qwen"],
            "trade_setup": ["groq_70b", "openrouter_nemotron", "openrouter_qwen"],
            "triage": ["groq_70b", "cerebras_70b"],
        }
        return ensembles.get(task_type, ["groq_70b", "openrouter_qwen"])

    def _get_provider(self, name: str):
        """Get provider by name (handles multi-key)"""
        if name in self.multi_key_providers:
            return self.multi_key_providers[name]
        return self.providers.get(name)

    # ─────────────────────────────────────────────────────────────────────────
    # STATS & MONITORING
    # ─────────────────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Get usage stats for all providers"""
        stats = {}
        for name, provider in self.multi_key_providers.items():
            stats[name] = provider.get_stats()
        for name, provider in self.providers.items():
            stats[name] = provider.get_stats()
        return stats

    def reset_stats(self):
        """Reset all provider stats"""
        for provider in self.multi_key_providers.values():
            provider.stats = type(provider.stats)()
        for provider in self.providers.values():
            provider.stats = ProviderStats()


# Global singleton
_orchestrator: Optional[EnsembleOrchestrator] = None


def get_orchestrator() -> EnsembleOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = EnsembleOrchestrator()
    return _orchestrator


def reset_orchestrator():
    global _orchestrator
    _orchestrator = None