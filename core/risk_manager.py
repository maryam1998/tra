"""
Risk Manager — deliberately has ZERO dependency on the AI agent.

This module is the last gate before anything reaches Telegram. It:
  1. Computes position size from account risk %, not from the AI.
  2. Computes margin / liquidation price for leveraged setups.
  3. Rejects or scales down anything that violates hard limits
     (max leverage, max risk per trade, minimum distance between
     stop-loss and liquidation, max exposure per symbol).

Even if the AI agent were compromised or hallucinating, this module
alone prevents dangerous leverage or position sizes from ever being
suggested to the user.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.models import Direction, Portfolio, RiskDecision


@dataclass
class RiskLimits:
    max_risk_per_trade_pct: float
    max_leverage: float
    min_liquidation_buffer_mult: float
    max_portfolio_exposure_pct: float


class RiskManager:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    @staticmethod
    def _maintenance_margin_rate(leverage: float) -> float:
        """
        Conservative approximation of exchange maintenance margin
        rate as a function of leverage. Higher leverage -> higher
        maintenance margin rate, but MUST always stay strictly below
        1/leverage — otherwise the liquidation price formula flips
        to the wrong side of entry (a mathematically invalid state
        where the position would be "liquidated" before it even
        opens). Replace with the exchange's real tiered schedule if
        available via API.
        """
        mmr = min(0.004 * leverage, 0.01)
        return min(mmr, 0.5 / leverage)

    def compute_liquidation_price(
        self, entry: float, leverage: float, direction: Direction
    ) -> float:
        mmr = self._maintenance_margin_rate(leverage)
        # Isolated-margin approximation:
        #   long liquidation  = entry * (1 - 1/leverage + mmr)
        #   short liquidation = entry * (1 + 1/leverage - mmr)
        if direction == Direction.LONG:
            liq = entry * (1 - (1 / leverage) + mmr)
            assert liq < entry, "Invalid state: long liquidation price must be below entry"
        else:
            liq = entry * (1 + (1 / leverage) - mmr)
            assert liq > entry, "Invalid state: short liquidation price must be above entry"
        return liq

    def compute_position_size(
        self,
        entry: float,
        stop_loss: float,
        free_capital_quote: float,
    ) -> tuple[float, float]:
        """
        Position size such that hitting the stop-loss loses exactly
        max_risk_per_trade_pct of free capital.
        Returns (position_size_in_base_units, risk_amount_in_quote).
        """
        risk_amount = free_capital_quote * (self.limits.max_risk_per_trade_pct / 100.0)
        stop_distance = abs(entry - stop_loss)
        if stop_distance <= 0:
            return 0.0, 0.0
        position_size = risk_amount / stop_distance
        return position_size, risk_amount

    def evaluate(
        self,
        direction: Direction,
        entry: float,
        stop_loss: float,
        take_profit: float,
        proposed_leverage: float,
        portfolio: Portfolio,
        symbol_current_exposure_quote: float = 0.0,
    ) -> RiskDecision:
        # 1. Clamp leverage to the hard cap regardless of what was proposed.
        leverage = max(1.0, min(proposed_leverage, self.limits.max_leverage))

        # 2. Position sizing from account risk, independent of any AI output.
        position_size, risk_amount = self.compute_position_size(
            entry, stop_loss, portfolio.free_capital_quote
        )
        if position_size <= 0:
            return RiskDecision(
                approved=False,
                reason="Invalid stop distance (entry == stop_loss) — cannot size position.",
                leverage=leverage,
                position_size=0.0,
                position_value_quote=0.0,
                margin_required=0.0,
                liquidation_price=None,
                liquidation_distance_pct=None,
                risk_amount_quote=0.0,
            )

        position_value_quote = position_size * entry
        margin_required = position_value_quote / leverage

        # 3. Exposure cap: this trade's notional value vs total portfolio.
        projected_exposure_quote = symbol_current_exposure_quote + position_value_quote
        exposure_pct = portfolio.exposure_pct(projected_exposure_quote)
        if exposure_pct > self.limits.max_portfolio_exposure_pct:
            return RiskDecision(
                approved=False,
                reason=(
                    f"Rejected: projected exposure {exposure_pct:.1f}% exceeds "
                    f"max allowed {self.limits.max_portfolio_exposure_pct:.1f}%."
                ),
                leverage=leverage,
                position_size=position_size,
                position_value_quote=position_value_quote,
                margin_required=margin_required,
                liquidation_price=None,
                liquidation_distance_pct=None,
                risk_amount_quote=risk_amount,
            )

        # 4. Margin sufficiency.
        if margin_required > portfolio.free_capital_quote:
            return RiskDecision(
                approved=False,
                reason=(
                    f"Rejected: required margin ({margin_required:.2f}) exceeds "
                    f"free capital ({portfolio.free_capital_quote:.2f})."
                ),
                leverage=leverage,
                position_size=position_size,
                position_value_quote=position_value_quote,
                margin_required=margin_required,
                liquidation_price=None,
                liquidation_distance_pct=None,
                risk_amount_quote=risk_amount,
            )

        # 5. Liquidation safety: stop-loss must trigger well before
        #    liquidation. If it wouldn't, de-leverage step by step;
        #    if even leverage=1 can't satisfy the buffer, reject.
        liquidation_price = None
        liquidation_distance_pct = None
        while leverage >= 1.0:
            liq_price = self.compute_liquidation_price(entry, leverage, direction)
            stop_distance = abs(entry - stop_loss)
            liq_distance = abs(entry - liq_price)

            if direction == Direction.LONG and liq_price >= stop_loss:
                # liquidation would trigger before or at the stop — unsafe
                leverage -= 0.5
                continue
            if direction == Direction.SHORT and liq_price <= stop_loss:
                leverage -= 0.5
                continue

            if liq_distance < stop_distance * self.limits.min_liquidation_buffer_mult:
                leverage -= 0.5
                continue

            liquidation_price = liq_price
            liquidation_distance_pct = (liq_distance / entry) * 100.0
            break
        else:
            return RiskDecision(
                approved=False,
                reason=(
                    "Rejected: no leverage level (down to 1x) keeps the "
                    "liquidation price a safe distance beyond the stop-loss."
                ),
                leverage=1.0,
                position_size=position_size,
                position_value_quote=position_value_quote,
                margin_required=margin_required,
                liquidation_price=None,
                liquidation_distance_pct=None,
                risk_amount_quote=risk_amount,
            )

        if leverage < 1.0:
            return RiskDecision(
                approved=False,
                reason="Rejected: could not find a safe leverage >= 1x.",
                leverage=1.0,
                position_size=position_size,
                position_value_quote=position_value_quote,
                margin_required=margin_required,
                liquidation_price=None,
                liquidation_distance_pct=None,
                risk_amount_quote=risk_amount,
            )

        # Recompute margin at the (possibly reduced) final leverage.
        margin_required = position_value_quote / leverage

        return RiskDecision(
            approved=True,
            reason="Approved within risk limits.",
            leverage=leverage,
            position_size=position_size,
            position_value_quote=position_value_quote,
            margin_required=margin_required,
            liquidation_price=liquidation_price,
            liquidation_distance_pct=liquidation_distance_pct,
            risk_amount_quote=risk_amount,
        )
