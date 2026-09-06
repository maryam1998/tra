"""
Derives entry / stop-loss / take-profit purely from TechnicalSignal
(ATR + support/resistance). No AI or guesswork involved — this is
the numeric backbone the AI agent is explicitly barred from touching.
"""
from __future__ import annotations

from core.models import Direction, TechnicalSignal

ATR_STOP_MULT = 1.5
MIN_RISK_REWARD = 1.5


def compute_levels(technical: TechnicalSignal, direction: Direction) -> tuple[float, float, float]:
    entry = technical.last_price
    atr = max(technical.atr, entry * 0.001)  # guard against a near-zero ATR on illiquid data

    if direction == Direction.LONG:
        atr_stop = entry - ATR_STOP_MULT * atr
        stop_loss = max(atr_stop, technical.support * 0.999)  # don't place stop below structural support
        risk = entry - stop_loss
        structural_target = technical.resistance
        take_profit = structural_target if structural_target > entry + risk * MIN_RISK_REWARD \
            else entry + risk * MIN_RISK_REWARD
    else:  # SHORT
        atr_stop = entry + ATR_STOP_MULT * atr
        stop_loss = min(atr_stop, technical.resistance * 1.001)
        risk = stop_loss - entry
        structural_target = technical.support
        take_profit = structural_target if structural_target < entry - risk * MIN_RISK_REWARD \
            else entry - risk * MIN_RISK_REWARD

    return entry, stop_loss, take_profit
