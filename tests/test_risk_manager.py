import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.models import Direction, Portfolio, WalletBalance
from core.risk_manager import RiskLimits, RiskManager


def make_portfolio(free_capital=1000.0, total_value=1000.0):
    return Portfolio(
        balances=[WalletBalance("USDT", total_value, free_capital, total_value)],
        total_value_quote=total_value,
        free_capital_quote=free_capital,
        quote_currency="USDT",
    )


def test_position_sizing_matches_risk_percent():
    rm = RiskManager(RiskLimits(1.0, 3.0, 2.0, 30.0))
    entry, stop = 100.0, 95.0
    size, risk_amount = rm.compute_position_size(entry, stop, free_capital_quote=1000.0)
    assert abs(risk_amount - 10.0) < 1e-6  # 1% of 1000
    assert abs(size - (10.0 / 5.0)) < 1e-6  # risk / stop_distance
    print(f"size={size:.4f} risk_amount={risk_amount:.2f}")


def test_configured_leverage_ceiling_is_never_exceeded():
    # Production-like config: MAX_LEVERAGE=3 (the .env.example default).
    rm = RiskManager(RiskLimits(max_risk_per_trade_pct=1.0, max_leverage=3.0,
                                 min_liquidation_buffer_mult=2.0, max_portfolio_exposure_pct=100.0))
    portfolio = make_portfolio(free_capital=1000.0, total_value=1000.0)
    decision = rm.evaluate(
        direction=Direction.LONG,
        entry=100.0,
        stop_loss=99.0,       # 1% stop
        take_profit=105.0,
        proposed_leverage=20.0,  # AI/user asks for far more than the ceiling
        portfolio=portfolio,
    )
    print(f"decision approved={decision.approved} leverage={decision.leverage} "
          f"liq_price={decision.liquidation_price} reason={decision.reason}")
    assert decision.leverage <= 3.0, "Configured max leverage must never be exceeded"
    if decision.approved:
        assert decision.liquidation_price < decision.liquidation_price + 1  # sanity
        assert decision.liquidation_distance_pct >= 2.0 - 1e-6


def test_liquidation_price_never_flips_side_of_entry_at_high_leverage():
    rm = RiskManager(RiskLimits(max_risk_per_trade_pct=1.0, max_leverage=50.0,
                                 min_liquidation_buffer_mult=1.0, max_portfolio_exposure_pct=100.0))
    for lev in [1, 2, 5, 10, 20, 30, 50]:
        long_liq = rm.compute_liquidation_price(100.0, lev, Direction.LONG)
        short_liq = rm.compute_liquidation_price(100.0, lev, Direction.SHORT)
        assert long_liq < 100.0, f"long liquidation must stay below entry at {lev}x (got {long_liq})"
        assert short_liq > 100.0, f"short liquidation must stay above entry at {lev}x (got {short_liq})"
    print("liquidation price stays on the correct side of entry at all tested leverage levels")


def test_exposure_cap_rejects_oversized_trade():
    rm = RiskManager(RiskLimits(max_risk_per_trade_pct=50.0, max_leverage=5.0,
                                 min_liquidation_buffer_mult=1.5, max_portfolio_exposure_pct=10.0))
    portfolio = make_portfolio(free_capital=1000.0, total_value=1000.0)
    decision = rm.evaluate(
        direction=Direction.LONG,
        entry=100.0,
        stop_loss=90.0,
        take_profit=120.0,
        proposed_leverage=2.0,
        portfolio=portfolio,
    )
    print(f"exposure-capped decision approved={decision.approved} reason={decision.reason}")
    assert not decision.approved


def test_insufficient_margin_rejected():
    rm = RiskManager(RiskLimits(max_risk_per_trade_pct=90.0, max_leverage=1.0,
                                 min_liquidation_buffer_mult=1.0, max_portfolio_exposure_pct=100.0))
    portfolio = make_portfolio(free_capital=50.0, total_value=50.0)
    decision = rm.evaluate(
        direction=Direction.LONG,
        entry=100.0,
        stop_loss=50.0,
        take_profit=150.0,
        proposed_leverage=1.0,
        portfolio=portfolio,
    )
    print(f"margin decision approved={decision.approved} reason={decision.reason}")
    assert not decision.approved


if __name__ == "__main__":
    test_position_sizing_matches_risk_percent()
    test_configured_leverage_ceiling_is_never_exceeded()
    test_liquidation_price_never_flips_side_of_entry_at_high_leverage()
    test_exposure_cap_rejects_oversized_trade()
    test_insufficient_margin_rejected()
    print("All risk_manager tests passed.")
