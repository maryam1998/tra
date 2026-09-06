"""
Minimal Telegram notifier — plain HTTP calls to the Bot API, no extra
dependency needed. Only ever sends a message when the scanner has
already decided (via AI + RiskManager) that an opportunity is worth
surfacing; sending nothing is a first-class, expected outcome of a
scan cycle.
"""
from __future__ import annotations

import requests

from core.models import Opportunity


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, timeout: int = 10):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def _send(self, text: str) -> None:
        if not self.is_configured:
            raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not configured")
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        resp = requests.post(
            url, json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}, timeout=self.timeout
        )
        resp.raise_for_status()

    def format_opportunity(self, opp: Opportunity) -> str:
        arrow = "🟢 LONG" if opp.direction.value == "long" else "🔴 SHORT"
        liq = f"{opp.liquidation_price:.4f}" if opp.liquidation_price else "n/a"
        return (
            f"<b>{arrow} — {opp.symbol}</b> ({opp.asset_class.value})\n"
            f"Score: {opp.composite_score:.0f}/100  |  AI conviction: {opp.ai.conviction:.0f}  "
            f"(source: {opp.ai.source})\n\n"
            f"Entry: <b>{opp.entry_price:.4f}</b>\n"
            f"Stop Loss: <b>{opp.stop_loss:.4f}</b>\n"
            f"Take Profit: <b>{opp.take_profit:.4f}</b>\n"
            f"Leverage: <b>{opp.leverage:.1f}x</b>  |  Margin: {opp.margin_required:.2f} "
            f"{opp.technical.asset_class.value}\n"
            f"Liquidation: {liq} (buffer {opp.liquidation_distance_pct or 0:.1f}%)\n"
            f"Risk this trade: {opp.risk_amount_quote:.2f}\n\n"
            f"<i>{opp.ai.rationale}</i>\n\n"
            f"⚠️ Analysis only — no order has been placed."
        )

    def send_opportunity(self, opp: Opportunity) -> None:
        self._send(self.format_opportunity(opp))

    def send_text(self, text: str) -> None:
        self._send(text)
