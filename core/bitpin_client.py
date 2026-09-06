"""
Bitpin API client.

Responsibilities in this architecture:
  - Authenticate and fetch the user's wallet balances / portfolio.
  - Fetch current tickers for the user's crypto watchlist (used as
    the authoritative current price / orderbook reference for
    anything the user might eventually act on at Bitpin).

Historical OHLCV for indicator calculation is intentionally NOT
sourced from Bitpin here (see core/market_data.py) — Bitpin's public
API is oriented around markets/orderbook/wallets, not candle history,
so a dedicated crypto OHLCV provider is used for technical analysis
while Bitpin remains the source of truth for the user's own balances.

IMPORTANT: exact endpoint paths below are based on Bitpin's published
client SDKs at the time this was written. Because this environment
has no live internet access to re-verify against
https://docs.bitpin.org at build time, treat the endpoint constants
below as a single, clearly-marked place to double check / adjust
once you test against a real API key — nothing else in the codebase
needs to change if a path differs.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import requests

from core.models import Portfolio, WalletBalance


class BitpinAuthError(Exception):
    pass


class BitpinClient:
    # --- Endpoint map: the one place to fix if Bitpin's paths differ ---
    EP_LOGIN = "/api/v1/usr/authenticate/"
    EP_REFRESH = "/api/v1/usr/refresh_token/"
    EP_WALLETS = "/api/v1/wlt/wallets/"
    EP_MARKETS = "/api/v1/mkt/markets/"
    EP_TICKER = "/api/v1/mkt/tickers/"
    EP_ORDERBOOK = "/api/v1/mkt/orderbooks/{symbol}/"

    def __init__(self, api_key: str, secret_key: str, base_url: str, timeout: int = 15):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self.session = requests.Session()

    # ---------------------------------------------------------------- #
    # Auth
    # ---------------------------------------------------------------- #
    def authenticate(self) -> None:
        if not self.api_key or not self.secret_key:
            raise BitpinAuthError(
                "BITPIN_API_KEY / BITPIN_SECRET_KEY are not set — cannot authenticate."
            )
        resp = self.session.post(
            self.base_url + self.EP_LOGIN,
            json={"api_key": self.api_key, "secret_key": self.secret_key},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data.get("access") or data.get("access_token")
        self._refresh_token = data.get("refresh") or data.get("refresh_token")
        if not self._access_token:
            raise BitpinAuthError(f"Unexpected Bitpin auth response shape: {data}")

    def _headers(self) -> Dict[str, str]:
        if not self._access_token:
            self.authenticate()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _get(self, path: str, **kwargs) -> dict:
        resp = self.session.get(self.base_url + path, headers=self._headers(), timeout=self.timeout, **kwargs)
        if resp.status_code == 401:
            # token expired — re-authenticate once and retry
            self.authenticate()
            resp = self.session.get(self.base_url + path, headers=self._headers(), timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp.json()

    # ---------------------------------------------------------------- #
    # Public data (no auth strictly required, but kept consistent)
    # ---------------------------------------------------------------- #
    def get_markets(self) -> List[dict]:
        data = self.session.get(self.base_url + self.EP_MARKETS, timeout=self.timeout).json()
        return data if isinstance(data, list) else data.get("results", [])

    def get_ticker(self, symbol: str) -> dict:
        data = self.session.get(self.base_url + self.EP_TICKER, timeout=self.timeout).json()
        rows = data if isinstance(data, list) else data.get("results", [])
        for row in rows:
            if row.get("symbol") == symbol or row.get("code") == symbol:
                return row
        raise ValueError(f"Symbol {symbol} not found in Bitpin ticker list")

    # ---------------------------------------------------------------- #
    # Private (authenticated) data
    # ---------------------------------------------------------------- #
    def get_wallets_raw(self) -> List[dict]:
        data = self._get(self.EP_WALLETS)
        return data if isinstance(data, list) else data.get("results", [])

    def get_portfolio(self, quote_currency: str = "USDT") -> Portfolio:
        """
        Builds a normalized Portfolio from raw wallet balances.
        Valuation into `quote_currency` uses ticker lookups for each
        non-quote asset; assets with no direct market are valued at 0
        rather than guessed.
        """
        raw = self.get_wallets_raw()
        balances: List[WalletBalance] = []
        total_value = 0.0

        for w in raw:
            currency = w.get("asset") or w.get("currency") or w.get("code", "")
            total = float(w.get("balance", w.get("total", 0)) or 0)
            available = float(w.get("available", w.get("free", total)) or 0)

            if currency.upper() == quote_currency.upper():
                value = total
            else:
                try:
                    ticker = self.get_ticker(f"{currency}_{quote_currency}")
                    price = float(ticker.get("price", ticker.get("last", 0)))
                    value = total * price
                except Exception:
                    value = 0.0

            total_value += value
            balances.append(WalletBalance(currency=currency, total=total, available=available, value_in_quote=value))

        free_capital = next(
            (b.available for b in balances if b.currency.upper() == quote_currency.upper()), 0.0
        )

        return Portfolio(
            balances=balances,
            total_value_quote=total_value,
            free_capital_quote=free_capital,
            quote_currency=quote_currency,
        )
