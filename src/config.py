"""
AlphaScout Configuration Module
Loads all YAML configs and validates API keys
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache

CONFIG_DIR = Path(__file__).parent.parent / "config"
DATA_DIR = Path(__file__).parent.parent / "data"


@lru_cache(maxsize=4)
def get_config(name: str) -> Dict[str, Any]:
    """Load any config file by name (without .yaml)"""
    path = CONFIG_DIR / f"{name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_settings() -> Dict[str, Any]:
    """Load main settings.yaml"""
    path = CONFIG_DIR / "settings.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_sectors() -> Dict[str, Any]:
    """Load sectors.yaml"""
    path = CONFIG_DIR / "sectors.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_providers() -> Dict[str, Any]:
    """Load providers.yaml"""
    path = CONFIG_DIR / "providers.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_sources() -> Dict[str, Any]:
    """Load sources.yaml"""
    path = CONFIG_DIR / "sources.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def get_setting(key: str, default=None):
    """Get nested setting by dot notation (e.g., 'schedule.run_times')"""
    settings = load_settings()
    keys = key.split(".")
    for k in keys:
        if isinstance(settings, dict):
            settings = settings.get(k)
        else:
            return default
        if settings is None:
            return default
    return settings


def get_enabled_sources() -> list:
    """Get all enabled news sources"""
    sources_data = load_sources()
    return [s for s in sources_data.get("sources", []) if s.get("enabled", True)]


def get_sources_by_category(category: str) -> list:
    """Get sources filtered by category"""
    return [s for s in get_enabled_sources() if s.get("category") == category]


def get_sector_keywords(sector: str) -> list:
    """Get keywords for a sector"""
    sectors = load_sectors()
    return sectors.get("sectors", {}).get(sector, {}).get("keywords", [])


def get_sector_tickers(sector: str) -> list:
    """Get known tickers for a sector"""
    sectors = load_sectors()
    return sectors.get("sectors", {}).get(sector, {}).get("tickers", [])


def get_all_sector_tickers() -> Dict[str, list]:
    """Get all sector tickers as {sector: [tickers]}"""
    sectors = load_sectors()
    result = {}
    for sector, data in sectors.get("sectors", {}).items():
        result[sector] = data.get("tickers", [])
    return result


def get_all_sector_keywords() -> Dict[str, list]:
    """Get all sector keywords combined"""
    sectors = load_sectors()
    result = {}
    for sector, data in sectors.get("sectors", {}).items():
        result[sector] = data.get("keywords", [])
    return result


def get_provider_config(provider: str) -> dict:
    """Get provider configuration"""
    providers = load_providers()
    return providers.get("providers", {}).get(provider, {})


def get_task_routing(task: str) -> dict:
    """Get routing config for a task"""
    providers = load_providers()
    return providers.get("task_routing", {}).get(task, {})


def get_ensemble_config() -> dict:
    """Get ensemble configuration"""
    providers = load_providers()
    return providers.get("ensemble", {})


def get_tokens_config() -> dict:
    """Get token limits per task"""
    settings = load_settings()
    return settings.get("tokens", {})


def validate_api_keys() -> Dict[str, bool]:
    """Check which API keys are configured"""
    keys = {
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY"),
        "GROQ_API_KEY_2": os.getenv("GROQ_API_KEY_2"),
        "GROQ_API_KEY_3": os.getenv("GROQ_API_KEY_3"),
        "GROQ_API_KEY_4": os.getenv("GROQ_API_KEY_4"),
        "GROQ_API_KEY_5": os.getenv("GROQ_API_KEY_5"),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
        "CEREBRAS_API_KEY": os.getenv("CEREBRAS_API_KEY"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "KITE_API_KEY": os.getenv("KITE_API_KEY"),
        "KITE_API_SECRET": os.getenv("KITE_API_SECRET"),
        "KITE_ACCESS_TOKEN": os.getenv("KITE_ACCESS_TOKEN"),
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
    }

    # Also check multi-key rotation for Groq
    groq_keys = [k for k, v in keys.items() if k.startswith("GROQ_API_KEY") and v]

    return {
        "groq": len(groq_keys) > 0,
        "groq_key_count": len(groq_keys),
        "openrouter": bool(keys["OPENROUTER_API_KEY"]),
        "cerebras": bool(keys["CEREBRAS_API_KEY"]),
        "gemini": bool(keys["GEMINI_API_KEY"]),
        "kite": all([keys["KITE_API_KEY"], keys["KITE_API_SECRET"], keys["KITE_ACCESS_TOKEN"]]),
        "telegram": all([keys["TELEGRAM_BOT_TOKEN"], keys["TELEGRAM_CHAT_ID"]]),
        "details": {k: bool(v) for k, v in keys.items()},
    }


def get_risk_config() -> dict:
    """Get risk management settings"""
    settings = load_settings()
    return settings.get("risk", {})


def get_signals_config() -> dict:
    """Get signal quality gates"""
    settings = load_settings()
    return settings.get("signals", {})


def get_screening_config() -> dict:
    """Get screening trigger settings (Session 8 backtest winners)"""
    settings = load_settings()
    return settings.get("screening", {})


def get_universe_config() -> dict:
    """Get universe filter settings"""
    settings = load_settings()
    return settings.get("universe", {})


def get_technical_config() -> dict:
    """Get technical analysis settings"""
    settings = load_settings()
    return settings.get("technical", {})


def get_schedule_config() -> dict:
    """Get schedule settings"""
    settings = load_settings()
    return settings.get("schedule", {})


def get_research_config() -> dict:
    """Get web research settings"""
    settings = load_settings()
    return settings.get("research", {})


# For backward compatibility
__all__ = [
    "load_settings",
    "load_sectors",
    "load_providers",
    "load_sources",
    "get_setting",
    "get_enabled_sources",
    "get_sources_by_category",
    "get_sector_keywords",
    "get_sector_tickers",
    "get_all_sector_keywords",
    "get_provider_config",
    "get_task_routing",
    "get_ensemble_config",
    "get_tokens_config",
    "validate_api_keys",
    "get_risk_config",
    "get_signals_config",
    "get_universe_config",
    "get_technical_config",
    "get_schedule_config",
    "get_research_config",
]