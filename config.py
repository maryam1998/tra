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

    # AI agent
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

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
