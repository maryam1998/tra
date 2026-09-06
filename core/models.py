"""
Shared data structures passed between pipeline stages:

    Scheduler -> Scanner -> TechnicalAnalysis -> News -> Portfolio
        -> AIAgent -> RiskManager -> Telegram

Keeping these as plain dataclasses (not dicts) makes the contract
between modules explicit and type-checkable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    STOCK = "stock"
    FOREX = "forex"
    GOLD = "gold"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


@dataclass
class Candle:
    timestamp: int  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class TechnicalSignal:
    symbol: str
    asset_class: AssetClass
    last_price: float
    ema_fast: float
    ema_slow: float
    rsi: float
    macd: float
    macd_signal: float
    macd_hist: float
    atr: float
    volume_ratio: float          # current volume / average volume
    momentum: float              # % change over N periods
    support: float
    resistance: float
    score: float                 # 0-100 composite technical score
    bias: Direction              # rule-based directional lean


@dataclass
class NewsAssessment:
    symbol: str
    headlines: List[str] = field(default_factory=list)
    sentiment_score: float = 0.0  # -1 (very negative) .. +1 (very positive)
    has_high_impact_event: bool = False
    summary: str = ""


@dataclass
class WalletBalance:
    currency: str
    total: float
    available: float
    value_in_quote: float = 0.0  # e.g. valued in IRT or USDT


@dataclass
class Portfolio:
    balances: List[WalletBalance] = field(default_factory=list)
    total_value_quote: float = 0.0
    free_capital_quote: float = 0.0
    quote_currency: str = "USDT"

    def exposure_pct(self, symbol_value: float) -> float:
        if self.total_value_quote <= 0:
            return 0.0
        return (symbol_value / self.total_value_quote) * 100.0


@dataclass
class AIAssessment:
    """
    Output of the AI Agent. Deliberately contains NO price/quantity
    numbers — the agent may only express direction, conviction and
    reasoning. All numeric trade parameters are computed in Python
    from TechnicalSignal + RiskManager, never from model text.
    """
    symbol: str
    direction: Direction
    conviction: float  # 0-100
    rationale: str
    source: str = "ai"  # "ai" or "rule_based_fallback"


@dataclass
class Opportunity:
    symbol: str
    asset_class: AssetClass
    direction: Direction
    technical: TechnicalSignal
    news: NewsAssessment
    ai: AIAssessment
    entry_price: float
    stop_loss: float
    take_profit: float
    composite_score: float
    leverage: float = 1.0
    position_size: float = 0.0        # in base asset units
    position_value_quote: float = 0.0  # in quote currency
    margin_required: float = 0.0
    liquidation_price: Optional[float] = None
    liquidation_distance_pct: Optional[float] = None
    risk_amount_quote: float = 0.0
    approved: bool = False
    rejection_reason: str = ""


@dataclass
class RiskDecision:
    approved: bool
    reason: str
    leverage: float
    position_size: float
    position_value_quote: float
    margin_required: float
    liquidation_price: Optional[float]
    liquidation_distance_pct: Optional[float]
    risk_amount_quote: float
