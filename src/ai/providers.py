"""
AI Provider Abstraction Layer
Unified interface for Groq, OpenRouter, Cerebras, Gemini with auto-fallback
"""
import os
import json
import time
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from threading import Lock
import logging
from pathlib import Path

# Ensure .env is loaded before reading API keys
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when provider hits rate limit"""
    pass


class ProviderError(Exception):
    """General provider error"""
    pass


@dataclass
class ProviderStats:
    calls: int = 0
    errors: int = 0
    rate_limits: int = 0
    last_call: float = 0
    last_error: str = ""

    def success_rate(self) -> float:
        if self.calls == 0:
            return 100.0
        return round((self.calls - self.errors) / self.calls * 100, 1)


@dataclass
class ModelConfig:
    name: str
    provider: str
    rpm: int = 30
    tpm: int = 6000
    best_for: List[str] = field(default_factory=list)
    max_tokens: int = 4096


class BaseProvider(ABC):
    """Abstract base class for all AI providers"""

    def __init__(self, api_key: str, name: str):
        self.api_key = api_key
        self.name = name
        self.stats = ProviderStats()
        self._lock = Lock()

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.1
    ) -> Optional[Dict]:
        """Generate completion and return parsed JSON"""
        pass

    def _track_call(self, success: bool = True, error: str = ""):
        with self._lock:
            self.stats.calls += 1
            self.stats.last_call = time.time()
            if not success:
                self.stats.errors += 1
                self.stats.last_error = error[:100]
                if "429" in error or "rate" in error.lower():
                    self.stats.rate_limits += 1

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Extract and parse JSON from response, with truncation recovery"""
        if not text:
            return None

        # Remove markdown code blocks
        text = text.strip()
        if "```" in text:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)
            else:
                parts = text.split("```")
                if len(parts) >= 2:
                    text = parts[1].replace("json", "").strip()

        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON object
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Truncation recovery: try to fix truncated JSON
        # Find the last complete key-value pair
        truncated_match = re.search(r'\{.*', text, re.DOTALL)
        if truncated_match:
            partial = truncated_match.group(0)
            # Try closing open strings and the object
            attempts = [
                partial + '"',           # Close an open string
                partial + '"}',          # Close string + object
                partial + '"}]',         # Close string + array + object
                partial + '"],"risks":[]}',  # Close string + risks array
            ]
            for attempt in attempts:
                try:
                    result = json.loads(attempt)
                    if result:
                        logger.debug(f"Recovered truncated JSON: {list(result.keys())}")
                        return result
                except json.JSONDecodeError:
                    continue

        logger.warning(f"Failed to parse JSON from {self.name}: {text[:200]}")
        return None

    def get_stats(self) -> Dict:
        return {
            "name": self.name,
            "calls": self.stats.calls,
            "errors": self.stats.errors,
            "rate_limits": self.stats.rate_limits,
            "success_rate": self.stats.success_rate(),
            "last_call_ago": round(time.time() - self.stats.last_call, 1) if self.stats.last_call else None
        }


class GroqProvider(BaseProvider):
    """Groq API - Llama models"""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        super().__init__(api_key, f"groq:{model}")
        try:
            from groq import Groq
            self.client = Groq(api_key=api_key)
            self.model = model
        except Exception as e:
            raise ProviderError(f"Failed to init Groq: {e}")

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.1
    ) -> Optional[Dict]:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            self._track_call(success=True)
            return self._parse_json(resp.choices[0].message.content)
        except Exception as e:
            self._track_call(success=False, error=str(e))
            if "429" in str(e) or "rate_limit" in str(e).lower():
                raise RateLimitError(f"Groq rate limited: {e}")
            raise ProviderError(f"Groq error: {e}")


class GroqMultiKeyProvider:
    """Groq with automatic key rotation"""

    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.model = model
        self.providers: List[GroqProvider] = []
        self.current_index = 0
        self._load_keys()

    def _load_keys(self):
        keys = []
        # Primary key
        key = os.environ.get("GROQ_API_KEY")
        if key:
            keys.append(key)
        # Additional keys (2-8)
        for i in range(2, 9):
            key = os.environ.get(f"GROQ_API_KEY_{i}")
            if key:
                keys.append(key)

        for key in keys:
            try:
                self.providers.append(GroqProvider(key, self.model))
            except Exception as e:
                logger.warning(f"Groq key failed: {e}")

        if not self.providers:
            raise ProviderError("No valid Groq API keys found!")

        logger.info(f"Loaded {len(self.providers)} Groq API keys")

    def _next_provider(self) -> GroqProvider:
        provider = self.providers[self.current_index % len(self.providers)]
        self.current_index += 1
        return provider

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.1,
        retries: int = 3
    ) -> Optional[Dict]:
        last_error = None

        for attempt in range(retries * len(self.providers)):
            provider = self._next_provider()
            try:
                return provider.generate(prompt, system, max_tokens, temperature)
            except RateLimitError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue

        raise ProviderError(f"All Groq keys exhausted. Last error: {last_error}")

    def get_stats(self) -> Dict:
        return {
            "name": f"groq_multi:{self.model}",
            "keys": len(self.providers),
            "providers": [p.get_stats() for p in self.providers]
        }


class OpenRouterProvider(BaseProvider):
    """OpenRouter API - Multiple free models"""

    def __init__(self, api_key: str, model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"):
        super().__init__(api_key, f"openrouter:{model}")
        self.model = model
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/alphascout",
            "X-Title": "AlphaScout"
        })

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.1
    ) -> Optional[Dict]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            resp = self.session.post(self.base_url, json=payload, timeout=20)
            if resp.status_code == 429:
                raise RateLimitError("OpenRouter rate limited")

            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            self._track_call(success=True)
            return self._parse_json(content)
        except RateLimitError:
            self._track_call(success=False, error="429")
            raise
        except Exception as e:
            self._track_call(success=False, error=str(e))
            raise ProviderError(f"OpenRouter error: {e}")


class CerebrasProvider(BaseProvider):
    """Cerebras API - Fast inference"""

    def __init__(self, api_key: str, model: str = "gpt-oss-120b"):
        super().__init__(api_key, f"cerebras:{model}")
        self.model = model
        self.base_url = "https://api.cerebras.ai/v1/chat/completions"
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.1
    ) -> Optional[Dict]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        try:
            resp = self.session.post(self.base_url, json=payload, timeout=20)
            if resp.status_code == 429:
                raise RateLimitError("Cerebras rate limited")

            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            self._track_call(success=True)
            return self._parse_json(content)
        except RateLimitError:
            self._track_call(success=False, error="429")
            raise
        except Exception as e:
            self._track_call(success=False, error=str(e))
            raise ProviderError(f"Cerebras error: {e}")


class GeminiProvider(BaseProvider):
    """Google Gemini API via REST"""

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite"):
        super().__init__(api_key, f"gemini:{model}")
        self.model = model
        self.base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        import requests
        self.session = requests.Session()

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.1
    ) -> Optional[Dict]:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        payload = {
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        try:
            resp = self.session.post(
                f"{self.base_url}?key={self.api_key}",
                json=payload,
                timeout=20
            )
            if resp.status_code == 429:
                raise RateLimitError("Gemini rate limited")

            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                raise ProviderError(f"Gemini API error: {data['error'].get('message', 'Unknown')}")

            candidates = data.get("candidates", [])
            if not candidates:
                raise ProviderError("Gemini returned no candidates")

            content = candidates[0]["content"]["parts"][0]["text"]
            self._track_call(success=True)
            return self._parse_json(content)
        except RateLimitError:
            self._track_call(success=False, error="429")
            raise
        except Exception as e:
            self._track_call(success=False, error=str(e))
            if "429" in str(e) or "quota" in str(e).lower():
                raise RateLimitError(f"Gemini rate limited: {e}")
            raise ProviderError(f"Gemini error: {e}")


class NVIDIANIMProvider(BaseProvider):
    """NVIDIA NIM API - Fast free inference"""

    def __init__(self, api_key: str, model: str = "meta/llama-3.1-70b-instruct"):
        super().__init__(api_key, f"nvidia_nim:{model}")
        self.model = model
        self.base_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.1
    ) -> Optional[Dict]:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }

        try:
            resp = self.session.post(self.base_url, json=payload, timeout=20)
            if resp.status_code == 429:
                raise RateLimitError("NVIDIA NIM rate limited")

            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            self._track_call(success=True)
            return self._parse_json(content)
        except RateLimitError:
            self._track_call(success=False, error="429")
            raise
        except Exception as e:
            self._track_call(success=False, error=str(e))
            raise ProviderError(f"NVIDIA NIM error: {e}")


class ProviderRegistry:
    """Manages all providers with routing and fallback"""

    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.routing: Dict[str, List[str]] = {}
        self._initialize()

    def _initialize(self):
        # Groq Multi-Key (Primary for reasoning)
        if os.environ.get("GROQ_API_KEY"):
            try:
                self.providers["groq_70b"] = GroqMultiKeyProvider("llama-3.3-70b-versatile")
            except Exception as e:
                logger.warning(f"Groq 70B init failed: {e}")

        # Groq 8B (Fast filter)
        if os.environ.get("GROQ_API_KEY"):
            try:
                self.providers["groq_8b"] = GroqMultiKeyProvider("llama-3.1-8b-instant")
            except Exception as e:
                logger.warning(f"Groq 8B init failed: {e}")

        # OpenRouter
        if os.environ.get("OPENROUTER_API_KEY"):
            try:
                self.providers["openrouter"] = OpenRouterProvider(
                    os.environ["OPENROUTER_API_KEY"],
                    "nvidia/nemotron-3-ultra-550b-a55b:free"
                )
            except Exception as e:
                logger.warning(f"OpenRouter init failed: {e}")

        # Cerebras
        if os.environ.get("CEREBRAS_API_KEY"):
            try:
                self.providers["cerebras"] = CerebrasProvider(
                    os.environ["CEREBRAS_API_KEY"],
                    "gpt-oss-120b"
                )
            except Exception as e:
                logger.warning(f"Cerebras init failed: {e}")

        # Gemini
        if os.environ.get("GEMINI_API_KEY"):
            try:
                self.providers["gemini"] = GeminiProvider(
                    os.environ["GEMINI_API_KEY"],
                    "gemini-3.1-flash-lite"
                )
            except Exception as e:
                logger.warning(f"Gemini init failed: {e}")

        # NVIDIA NIM
        if os.environ.get("NVIDIA_NIM_API_KEY"):
            try:
                self.providers["nvidia_nim"] = NVIDIANIMProvider(
                    os.environ["NVIDIA_NIM_API_KEY"],
                    "meta/llama-3.1-70b-instruct"
                )
            except Exception as e:
                logger.warning(f"NVIDIA NIM init failed: {e}")

        # Build routing — prioritize fast providers
        self.routing = {
            "triage": ["groq_8b", "groq_70b", "gemini", "cerebras"],
            "entity_extraction": ["groq_8b", "gemini", "groq_70b", "openrouter"],
            "impact_analysis": ["groq_70b", "gemini", "groq_8b", "cerebras"],
            "trade_setup": ["groq_70b", "gemini", "groq_8b", "openrouter"],
            "quick_filter": ["groq_8b", "gemini", "groq_70b", "cerebras"]
        }

        logger.info(f"Initialized providers: {list(self.providers.keys())}")

    def get_provider(self, name: str) -> Optional[BaseProvider]:
        return self.providers.get(name)

    def execute_task(
        self,
        task_type: str,
        system: str,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.1,
        require_ensemble: bool = False,
        ensemble_models: List[str] = None,
    ) -> Optional[Dict]:
        """Execute a task with optional ensemble requirement"""
        if require_ensemble and ensemble_models:
            # Use specific ensemble models
            results = []
            for model_name in ensemble_models:
                provider = self.providers.get(model_name)
                if not provider:
                    continue
                try:
                    result = provider.generate(prompt, system, max_tokens, temperature)
                    if result:
                        results.append({"provider": model_name, "result": result})
                except Exception as e:
                    logger.warning(f"Ensemble {model_name} failed: {e}")

            if len(results) >= 2:
                agreed = [r["result"] for r in results]
                return self._average_results(agreed)
            elif results:
                return results[0]["result"]
            return None
        else:
            return self.execute_with_fallback(task_type, prompt, system, max_tokens, temperature)

    def execute_with_fallback(
        self,
        task_type: str,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.1,
        min_agree: int = 2
    ) -> Optional[Dict]:
        """Execute with ensemble fallback"""
        route = self.routing.get(task_type, ["groq_70b", "cerebras", "openrouter", "gemini"])
        results = []

        for provider_name in route:
            provider = self.providers.get(provider_name)
            if not provider:
                continue

            try:
                result = provider.generate(prompt, system, max_tokens, temperature)
                if result:
                    results.append({"provider": provider_name, "result": result})
                    if len(results) >= min_agree:
                        break
            except RateLimitError:
                logger.warning(f"{provider_name} rate limited, trying next")
                continue
            except Exception as e:
                logger.warning(f"{provider_name} failed: {e}")
                continue

        if not results:
            return None

        if len(results) == 1:
            return results[0]["result"]

        # Ensemble agreement check
        return self._ensemble_agreement(results, min_agree)

    def _ensemble_agreement(self, results: List[Dict], min_agree: int) -> Optional[Dict]:
        """Check if models agree on direction and magnitude"""
        if len(results) < min_agree:
            return results[0]["result"]  # Return first if not enough

        # For trade signals, check direction agreement
        first = results[0]["result"]
        agreed = [first]

        for r in results[1:]:
            if self._signals_agree(first, r["result"]):
                agreed.append(r["result"])

        if len(agreed) >= min_agree:
            # Average numeric fields
            return self._average_results(agreed)

        return first  # Fallback to first

    def _signals_agree(self, a: Dict, b: Dict) -> bool:
        """Check if two trade signals agree on direction"""
        # Check trade_type / direction
        dir_a = a.get("trade_type", "").upper()
        dir_b = b.get("trade_type", "").upper()

        buy_types = {"STRONG_BUY", "BUY", "ACCUMULATE"}
        sell_types = {"SELL", "AVOID"}

        a_buy = dir_a in buy_types
        b_buy = dir_b in buy_types
        a_sell = dir_a in sell_types
        b_sell = dir_b in sell_types

        # Both bullish or both bearish
        if (a_buy and b_buy) or (a_sell and b_sell):
            # Check magnitude within tolerance
            tgt_a = a.get("target_pct", 0)
            tgt_b = b.get("target_pct", 0)
            if tgt_a and tgt_b:
                return abs(tgt_a - tgt_b) / max(tgt_a, tgt_b) < 0.3
            return True

        return False

    def _average_results(self, results: List[Dict]) -> Dict:
        """Average numeric fields across agreeing results"""
        base = results[0].copy()

        numeric_fields = ["target_pct", "stop_loss_pct", "hold_days", "confidence", "risk_reward", "expected_impact_pct"]
        for field in numeric_fields:
            values = [r.get(field) for r in results if r.get(field) is not None]
            if values:
                base[field] = round(sum(values) / len(values), 1)

        base["ensemble_size"] = len(results)
        base["ensemble_agreement"] = True
        return base

    def get_all_stats(self) -> Dict:
        return {name: p.get_stats() for name, p in self.providers.items()}


# Global registry instance
_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry