"""
Runs MarketScanner.run_cycle() on a fixed interval, forever, with no
user prompt required — this is what makes the system "autonomous":
the user never has to ask "what should I buy?"; the loop decides on
its own whether anything is worth surfacing, on every tick.

A single cycle raising an unexpected exception is logged and does
not kill the loop — one bad symbol or one flaky API must not take
the whole advisor down.
"""
from __future__ import annotations

import logging
import time

from core.scanner import MarketScanner


class Scheduler:
    def __init__(self, scanner: MarketScanner, interval_minutes: int, logger: logging.Logger):
        self.scanner = scanner
        self.interval_seconds = max(60, interval_minutes * 60)
        self.logger = logger

    def run_forever(self) -> None:
        self.logger.info(
            f"Scheduler started — scanning every {self.interval_seconds // 60} minutes. "
            f"Ctrl+C to stop."
        )
        while True:
            cycle_start = time.time()
            try:
                self.scanner.run_cycle()
            except Exception:
                self.logger.exception("Unhandled error during scan cycle — will retry next interval.")

            elapsed = time.time() - cycle_start
            sleep_for = max(1.0, self.interval_seconds - elapsed)
            self.logger.info(f"Cycle finished in {elapsed:.1f}s — sleeping {sleep_for:.0f}s.")
            time.sleep(sleep_for)

    def run_once(self):
        return self.scanner.run_cycle()
