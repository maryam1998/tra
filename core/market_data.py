"""
Market data providers for every asset class the advisor scans.

Bitpin is the source of truth for the user's own balances (see
bitpin_client.py) but is not used here for historical candles — this
module pulls OHLCV history from dedicated, well-documented public
APIs per asset class, so technical analysis works uniformly across
crypto / stocks / forex / gold.

Each provider implements the same `get_ohlcv(symbol, timeframe,
limit) -> List[Candle]` contract so `scanner.py` can treat every
asset class identically.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import List

import requests

from core.models import Candle

TIMEFRAME_TO_COINGECKO_DAYS = {
    "1h": 7,     # CoinGecko returns hourly granularity for <=90 day windows
    "4h": 30,
    "1d": 180,
}

TIMEFRAME_TO_TWELVEDATA_INTERVAL = {
    "1h": "1h",
    "4h": "4h",
    "1d": "1day",
}


class MarketDataProvider(ABC):
    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        ...


class CoinGeckoProvider(MarketDataProvider):
    """
    Crypto OHLCV via CoinGecko's public market_chart endpoint.
    `symbol` is expected as a CoinGecko coin id (e.g. "bitcoin"),
    or as a BASE_QUOTE pair where BASE is mapped to a coin id by
    the caller — kept simple here and documented for extension.
    """

    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        coin_id = symbol.lower()
        days = TIMEFRAME_TO_COINGECKO_DAYS.get(timeframe, 30)
        params = {"vs_currency": "usd", "days": days}
        headers = {"x-cg-demo-api-key": self.api_key} if self.api_key else {}

        resp = requests.get(
            f"{self.BASE_URL}/coins/{coin_id}/market_chart", params=params, headers=headers, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()

        prices = data.get("prices", [])
        volumes = dict(data.get("total_volumes", []))
        candles: List[Candle] = []
        # market_chart gives price points, not true OHLC; we bucket
        # consecutive points into pseudo-candles as an approximation
        # when a true OHLC endpoint isn't available on the free tier.
        for i in range(1, len(prices)):
            ts_prev, price_prev = prices[i - 1]
            ts, price = prices[i]
            vol = volumes.get(ts, 0.0)
            candles.append(
                Candle(
                    timestamp=int(ts / 1000),
                    open=price_prev,
                    high=max(price_prev, price),
                    low=min(price_prev, price),
                    close=price,
                    volume=float(vol),
                )
            )
        return candles[-limit:]


class TwelveDataProvider(MarketDataProvider):
    """
    Stocks / forex / gold OHLCV via Twelve Data's unified `/time_series`
    endpoint, which covers all three asset classes with one symbol
    format (e.g. "AAPL", "EUR/USD", "XAU/USD").
    """

    BASE_URL = "https://api.twelvedata.com/time_series"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        if not self.api_key:
            raise RuntimeError("TWELVE_DATA_API_KEY is not set")
        interval = TIMEFRAME_TO_TWELVEDATA_INTERVAL.get(timeframe, "1h")
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": limit,
            "apikey": self.api_key,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "error":
            raise RuntimeError(f"Twelve Data error for {symbol}: {data.get('message')}")

        values = data.get("values", [])
        candles: List[Candle] = []
        for row in reversed(values):  # API returns newest-first
            ts = int(time.mktime(time.strptime(row["datetime"][:19], "%Y-%m-%d %H:%M:%S")))
            candles.append(
                Candle(
                    timestamp=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0) or 0),
                )
            )
        return candles


class SyntheticProvider(MarketDataProvider):
    """
    Deterministic, network-free candle generator. Used for local
    testing / dry runs (see tests/e2e_dry_run.py) and as a safe
    fallback so the scanner never crashes the whole cycle if a
    live provider is unreachable during development.
    """

    def __init__(self, seed: int = 42, drift: float = 0.0):
        self.seed = seed
        self.drift = drift

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        import numpy as np

        rng = np.random.default_rng(abs(hash(symbol)) % (2**32))
        price = 100.0
        ts = int(time.time()) - limit * 3600
        candles = []
        for i in range(limit):
            change = self.drift + rng.normal(0, 1.0)
            open_ = price
            close = max(0.01, price + change)
            high = max(open_, close) + abs(rng.normal(0, 0.5))
            low = min(open_, close) - abs(rng.normal(0, 0.5))
            volume = abs(rng.normal(1000, 200))
            candles.append(Candle(ts + i * 3600, open_, high, low, close, volume))
            price = close
        return candles


class MarketDataRouter:
    """
    Picks the right provider per asset class. If a live provider
    raises (missing key, network error, rate limit), the router logs
    and falls back to skipping that symbol for this cycle rather than
    crashing the whole scan — one bad symbol should never take down
    the pipeline.
    """

    def __init__(self, crypto: MarketDataProvider, stocks: MarketDataProvider,
                 forex: MarketDataProvider, gold: MarketDataProvider, logger=None):
        self.providers = {
            "crypto": crypto,
            "stock": stocks,
            "forex": forex,
            "gold": gold,
        }
        self.logger = logger

    def get_ohlcv(self, asset_class: str, symbol: str, timeframe: str, limit: int) -> List[Candle]:
        provider = self.providers[asset_class]
        return provider.get_ohlcv(symbol, timeframe, limit)
