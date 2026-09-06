"""
Pure, dependency-light technical analysis.

Every number here comes from arithmetic on OHLCV data — nothing is
guessed or produced by a language model. This module is the single
source of truth for indicator values used later by the AI agent and
the risk manager.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from core.models import AssetClass, Candle, Direction, TechnicalSignal


def candles_to_df(candles: List[Candle]) -> pd.DataFrame:
    df = pd.DataFrame([c.__dict__ for c in candles])
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50.0)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def volume_ratio(df: pd.DataFrame, period: int = 20) -> float:
    avg_vol = df["volume"].rolling(period).mean().iloc[-1]
    if not avg_vol or np.isnan(avg_vol) or avg_vol == 0:
        return 1.0
    return float(df["volume"].iloc[-1] / avg_vol)


def momentum_pct(df: pd.DataFrame, period: int = 10) -> float:
    if len(df) <= period:
        return 0.0
    past = df["close"].iloc[-period - 1]
    now = df["close"].iloc[-1]
    if past == 0:
        return 0.0
    return float((now - past) / past * 100.0)


def support_resistance(df: pd.DataFrame, lookback: int = 50) -> tuple[float, float]:
    """
    Simple swing-based support/resistance: lowest low and highest
    high of the recent window, excluding the very last candle so the
    current price does not trivially become the extreme itself.
    """
    window = df.iloc[-(lookback + 1):-1] if len(df) > lookback + 1 else df.iloc[:-1]
    if window.empty:
        window = df
    support = float(window["low"].min())
    resistance = float(window["high"].max())
    return support, resistance


def composite_score(
    rsi_val: float,
    macd_hist: float,
    ema_fast: float,
    ema_slow: float,
    vol_ratio: float,
    momentum: float,
) -> tuple[float, Direction]:
    """
    Rule-based 0-100 score plus a directional bias. This score is
    what the AI agent's conviction is later blended with — it exists
    so that even in offline/no-AI mode the system can still rank
    opportunities purely on math.
    """
    trend_up = ema_fast > ema_slow
    score = 50.0

    # Trend component
    score += 15.0 if trend_up else -15.0

    # RSI component: reward pulling out of extremes in trend direction
    if trend_up:
        if 45 <= rsi_val <= 65:
            score += 10
        elif rsi_val > 75:
            score -= 10  # overbought, risky to chase
    else:
        if 35 <= rsi_val <= 55:
            score += 10
        elif rsi_val < 25:
            score -= 10  # oversold, risky to chase short

    # MACD histogram momentum confirmation
    if trend_up and macd_hist > 0:
        score += 10
    elif not trend_up and macd_hist < 0:
        score += 10
    else:
        score -= 5

    # Volume confirmation
    if vol_ratio > 1.3:
        score += 10
    elif vol_ratio < 0.6:
        score -= 5

    # Momentum alignment
    if trend_up and momentum > 0:
        score += 5
    elif not trend_up and momentum < 0:
        score += 5

    score = max(0.0, min(100.0, score))
    direction = Direction.LONG if trend_up else Direction.SHORT
    if 45 <= score <= 55:
        direction = Direction.NONE
    return score, direction


class TechnicalAnalyzer:
    def analyze(self, symbol: str, asset_class: AssetClass, candles: List[Candle]) -> TechnicalSignal:
        if len(candles) < 30:
            raise ValueError(f"Not enough candles for {symbol} to compute indicators (got {len(candles)})")

        df = candles_to_df(candles)
        close = df["close"]

        ema_fast_s = ema(close, 12)
        ema_slow_s = ema(close, 26)
        rsi_s = rsi(close, 14)
        macd_line, signal_line, hist = macd(close)
        atr_s = atr(df, 14)

        support, resistance = support_resistance(df)
        vol_ratio = volume_ratio(df)
        mom = momentum_pct(df)

        score, bias = composite_score(
            rsi_val=float(rsi_s.iloc[-1]),
            macd_hist=float(hist.iloc[-1]),
            ema_fast=float(ema_fast_s.iloc[-1]),
            ema_slow=float(ema_slow_s.iloc[-1]),
            vol_ratio=vol_ratio,
            momentum=mom,
        )

        return TechnicalSignal(
            symbol=symbol,
            asset_class=asset_class,
            last_price=float(close.iloc[-1]),
            ema_fast=float(ema_fast_s.iloc[-1]),
            ema_slow=float(ema_slow_s.iloc[-1]),
            rsi=float(rsi_s.iloc[-1]),
            macd=float(macd_line.iloc[-1]),
            macd_signal=float(signal_line.iloc[-1]),
            macd_hist=float(hist.iloc[-1]),
            atr=float(atr_s.iloc[-1]),
            volume_ratio=vol_ratio,
            momentum=mom,
            support=support,
            resistance=resistance,
            score=score,
            bias=bias,
        )
