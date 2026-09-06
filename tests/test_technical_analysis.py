import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from core.models import AssetClass, Candle
from core.technical_analysis import TechnicalAnalyzer


def make_trending_candles(n=120, start=100.0, drift=0.3, seed=1):
    rng = np.random.default_rng(seed)
    candles = []
    price = start
    ts = 1_700_000_000
    for i in range(n):
        change = drift + rng.normal(0, 1.0)
        open_ = price
        close = max(0.01, price + change)
        high = max(open_, close) + abs(rng.normal(0, 0.5))
        low = min(open_, close) - abs(rng.normal(0, 0.5))
        volume = abs(rng.normal(1000, 200))
        candles.append(Candle(ts + i * 3600, open_, high, low, close, volume))
        price = close
    return candles


def test_uptrend_produces_long_bias_and_valid_ranges():
    candles = make_trending_candles(drift=0.5)
    signal = TechnicalAnalyzer().analyze("TEST_UP", AssetClass.CRYPTO, candles)

    assert 0 <= signal.rsi <= 100
    assert signal.atr >= 0
    assert signal.support <= signal.last_price <= signal.resistance * 1.05 or signal.resistance >= signal.support
    assert 0 <= signal.score <= 100
    print(f"[uptrend] score={signal.score:.1f} bias={signal.bias} rsi={signal.rsi:.1f} "
          f"ema_fast={signal.ema_fast:.2f} ema_slow={signal.ema_slow:.2f}")


def test_downtrend_produces_short_bias():
    candles = make_trending_candles(drift=-0.5, seed=2)
    signal = TechnicalAnalyzer().analyze("TEST_DOWN", AssetClass.CRYPTO, candles)
    assert signal.ema_fast < signal.ema_slow
    print(f"[downtrend] score={signal.score:.1f} bias={signal.bias} rsi={signal.rsi:.1f}")


def test_insufficient_candles_raises():
    candles = make_trending_candles(n=5)
    try:
        TechnicalAnalyzer().analyze("TOO_SHORT", AssetClass.CRYPTO, candles)
        assert False, "Expected ValueError for insufficient candles"
    except ValueError:
        pass


if __name__ == "__main__":
    test_uptrend_produces_long_bias_and_valid_ranges()
    test_downtrend_produces_short_bias()
    test_insufficient_candles_raises()
    print("All technical_analysis tests passed.")
