"""
Prevents duplicate/spammy Telegram alerts.

An alert "key" is (symbol, direction). If the same symbol+direction
was already alerted within the cooldown window, it is suppressed.
State persists to a small JSON file so restarts don't cause re-alerts.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict


class AlertStore:
    def __init__(self, path: Path, cooldown_hours: float):
        self.path = path
        self.cooldown_seconds = cooldown_hours * 3600
        self._state: Dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._state = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._state = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

    @staticmethod
    def _key(symbol: str, direction: str) -> str:
        return f"{symbol}:{direction}"

    def should_alert(self, symbol: str, direction: str) -> bool:
        key = self._key(symbol, direction)
        last_sent = self._state.get(key)
        if last_sent is None:
            return True
        return (time.time() - last_sent) >= self.cooldown_seconds

    def mark_sent(self, symbol: str, direction: str) -> None:
        key = self._key(symbol, direction)
        self._state[key] = time.time()
        self._save()
