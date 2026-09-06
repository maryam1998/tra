"""
Central configuration for the AI Autonomous Financial Advisor.

Loads everything from a .env file (see .env.example) so no secret
or tunable parameter is ever hard-coded in the source.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from core.ai_providers import ProviderConfig

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _list(name: str, default: str = "") -> List[str]:
    raw = os.getenv(name, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    # Bitpin
    bitpin_api_key: str = os.getenv("BITPIN_API_KEY", "")
    bitpin_secret_key: str = os.getenv("BITPIN_SECRET_KEY", "")
    bitpin_base_url: str = os.getenv("BITPIN_BASE_URL", "https://api.bitpin.org")

    # Telegram
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")

    # AI agent — priority order in which free/paid LLM providers are tried.
    # Any name here with no key configured (and requires_key=True) is skipped.
    ai_provider_priority: List[str] = field(
        default_factory=lambda: _list(
            "AI_PROVIDER_PRIORITY",
            "anthropic,groq,openrouter,google_gemini,mistral,nvidia_nim,zai,"
            "huggingface,cloudflare,ollama_cloud,aionlabs,cohere,siliconflow,"
            "ovhcloud,llm7,kilocode,modelscope",
        )
    )

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

    google_gemini_api_key: str = os.getenv("GOOGLE_GEMINI_API_KEY", "")
    google_gemini_model: str = os.getenv("GOOGLE_GEMINI_MODEL", "gemini-2.5-flash")

    mistral_api_key: str = os.getenv("MISTRAL_API_KEY", "")
    mistral_model: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")

    nvidia_nim_api_key: str = os.getenv("NVIDIA_NIM_API_KEY", "")
    nvidia_nim_model: str = os.getenv("NVIDIA_NIM_MODEL", "meta/llama-3.3-70b-instruct")

    zai_api_key: str = os.getenv("ZAI_API_KEY", "")
    zai_model: str = os.getenv("ZAI_MODEL", "glm-4.7-flash")

    huggingface_api_key: str = os.getenv("HUGGINGFACE_API_KEY", "")
    huggingface_model: str = os.getenv("HUGGINGFACE_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")

    cloudflare_account_id: str = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    cloudflare_api_token: str = os.getenv("CLOUDFLARE_API_TOKEN", "")
    cloudflare_model: str = os.getenv("CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast")

    ollama_cloud_api_key: str = os.getenv("OLLAMA_CLOUD_API_KEY", "")
    ollama_cloud_model: str = os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b")

    aionlabs_api_key: str = os.getenv("AIONLABS_API_KEY", "")
    aionlabs_model: str = os.getenv("AIONLABS_MODEL", "aion-labs/aion-3.0-mini")

    cohere_api_key: str = os.getenv("COHERE_API_KEY", "")
    cohere_model: str = os.getenv("COHERE_MODEL", "command-r")

    siliconflow_api_key: str = os.getenv("SILICONFLOW_API_KEY", "")
    siliconflow_model: str = os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen3-8B")

    # OVHcloud's free tier is anonymous — no key needed at 2 RPM/IP/model.
    ovhcloud_api_key: str = os.getenv("OVHCLOUD_API_KEY", "")
    ovhcloud_model: str = os.getenv("OVHCLOUD_MODEL", "Meta-Llama-3_3-70B-Instruct")

    # LLM7.io's anonymous tier also needs no key (lower limits than a free token).
    llm7_api_key: str = os.getenv("LLM7_API_KEY", "")
    llm7_model: str = os.getenv("LLM7_MODEL", "gpt-oss:20b")

    # Kilo Code's free pool needs no API key at all.
    kilocode_model: str = os.getenv("KILOCODE_MODEL", "kilo-auto/free")

    modelscope_api_key: str = os.getenv("MODELSCOPE_API_KEY", "")
    modelscope_model: str = os.getenv("MODELSCOPE_MODEL", "Qwen/Qwen3.5-35B-A3B")

    # Market data provider keys
    coingecko_api_key: str = os.getenv("COINGECKO_API_KEY", "")
    twelve_data_api_key: str = os.getenv("TWELVE_DATA_API_KEY", "")
    alpha_vantage_api_key: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    metals_api_key: str = os.getenv("METALS_API_KEY", "")
    cryptopanic_api_key: str = os.getenv("CRYPTOPANIC_API_KEY", "")
    news_api_key: str = os.getenv("NEWS_API_KEY", "")

    # Watchlists
    watchlist_crypto: List[str] = field(default_factory=lambda: _list("WATCHLIST_CRYPTO"))
    watchlist_stocks: List[str] = field(default_factory=lambda: _list("WATCHLIST_STOCKS"))
    watchlist_forex: List[str] = field(default_factory=lambda: _list("WATCHLIST_FOREX"))
    watchlist_gold: List[str] = field(default_factory=lambda: _list("WATCHLIST_GOLD"))

    # Scheduler
    scan_interval_minutes: int = _int("SCAN_INTERVAL_MINUTES", 15)
    candle_timeframe: str = os.getenv("CANDLE_TIMEFRAME", "1h")
    candle_lookback: int = _int("CANDLE_LOOKBACK", 200)

    # Risk management
    max_risk_per_trade_pct: float = _float("MAX_RISK_PER_TRADE_PCT", 1.0)
    max_leverage: float = _float("MAX_LEVERAGE", 3.0)
    min_liquidation_buffer_mult: float = _float("MIN_LIQUIDATION_BUFFER_MULT", 2.0)
    max_portfolio_exposure_pct: float = _float("MAX_PORTFOLIO_EXPOSURE_PCT", 30.0)
    min_opportunity_score: float = _float("MIN_OPPORTUNITY_SCORE", 70.0)

    # Alerting
    alert_cooldown_hours: float = _float("ALERT_COOLDOWN_HOURS", 6.0)

    # Safety switch — must stay True until real order execution is
    # deliberately implemented and reviewed.
    dry_run_only: bool = _bool("DRY_RUN_ONLY", True)

    # Paths
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.logs_dir.mkdir(parents=True, exist_ok=True)


def build_ai_providers(s: "Settings") -> List[ProviderConfig]:
    """
    Build the ordered list of LLM providers to try, per AI_PROVIDER_PRIORITY.
    A provider is silently skipped later (by AIAgent) if it has no key and
    isn't one of the no-key free tiers (OVHcloud anonymous, LLM7 anonymous,
    Kilo Code).
    """
    catalog: dict[str, ProviderConfig] = {
        "anthropic": ProviderConfig(
            name="anthropic", kind="anthropic",
            base_url="https://api.anthropic.com/v1",
            model=s.anthropic_model, api_key=s.anthropic_api_key,
        ),
        "groq": ProviderConfig(
            name="groq", kind="openai",
            base_url="https://api.groq.com/openai/v1",
            model=s.groq_model, api_key=s.groq_api_key,
        ),
        "openrouter": ProviderConfig(
            name="openrouter", kind="openai",
            base_url="https://openrouter.ai/api/v1",
            model=s.openrouter_model, api_key=s.openrouter_api_key,
        ),
        "google_gemini": ProviderConfig(
            name="google_gemini", kind="openai",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            model=s.google_gemini_model, api_key=s.google_gemini_api_key,
        ),
        "mistral": ProviderConfig(
            name="mistral", kind="openai",
            base_url="https://api.mistral.ai/v1",
            model=s.mistral_model, api_key=s.mistral_api_key,
        ),
        "nvidia_nim": ProviderConfig(
            name="nvidia_nim", kind="openai",
            base_url="https://integrate.api.nvidia.com/v1",
            model=s.nvidia_nim_model, api_key=s.nvidia_nim_api_key,
        ),
        "zai": ProviderConfig(
            name="zai", kind="openai",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            model=s.zai_model, api_key=s.zai_api_key,
        ),
        "huggingface": ProviderConfig(
            name="huggingface", kind="openai",
            base_url="https://router.huggingface.co/v1",
            model=s.huggingface_model, api_key=s.huggingface_api_key,
        ),
        "cloudflare": ProviderConfig(
            name="cloudflare", kind="openai",
            base_url=(
                f"https://api.cloudflare.com/client/v4/accounts/{s.cloudflare_account_id}/ai/v1"
                if s.cloudflare_account_id else ""
            ),
            model=s.cloudflare_model, api_key=s.cloudflare_api_token,
        ),
        "ollama_cloud": ProviderConfig(
            name="ollama_cloud", kind="openai",
            base_url="https://ollama.com/v1",
            model=s.ollama_cloud_model, api_key=s.ollama_cloud_api_key,
        ),
        "aionlabs": ProviderConfig(
            name="aionlabs", kind="openai",
            base_url="https://api.aionlabs.ai/v1",
            model=s.aionlabs_model, api_key=s.aionlabs_api_key,
        ),
        "cohere": ProviderConfig(
            name="cohere", kind="cohere",
            base_url="https://api.cohere.com/v2",
            model=s.cohere_model, api_key=s.cohere_api_key,
        ),
        "siliconflow": ProviderConfig(
            name="siliconflow", kind="openai",
            base_url="https://api.siliconflow.cn/v1",
            model=s.siliconflow_model, api_key=s.siliconflow_api_key,
        ),
        "ovhcloud": ProviderConfig(
            name="ovhcloud", kind="openai",
            base_url="https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
            model=s.ovhcloud_model, api_key=s.ovhcloud_api_key,
            requires_key=False,  # free anonymous tier, 2 RPM/IP/model
        ),
        "llm7": ProviderConfig(
            name="llm7", kind="openai",
            base_url="https://api.llm7.io/v1",
            model=s.llm7_model, api_key=s.llm7_api_key,
            requires_key=False,  # anonymous access works, a token just raises limits
        ),
        "kilocode": ProviderConfig(
            name="kilocode", kind="openai",
            base_url="https://api.kilo.ai/api/gateway",
            model=s.kilocode_model, api_key="",
            requires_key=False,  # no API key at all for the free pool
        ),
        "modelscope": ProviderConfig(
            name="modelscope", kind="openai",
            base_url="https://api-inference.modelscope.cn/v1",
            model=s.modelscope_model, api_key=s.modelscope_api_key,
        ),
    }

    providers = []
    for name in s.ai_provider_priority:
        p = catalog.get(name.strip())
        if p is None:
            continue
        if p.base_url:  # e.g. cloudflare with no account id set yet
            providers.append(p)
    return providers
