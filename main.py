"""
AI Autonomous Financial Advisor — entry point.

Usage:
    python main.py            # run forever (autonomous scheduler)
    python main.py --once     # run exactly one scan cycle, then exit (for testing)

Architecture:
    Scheduler -> MarketScanner -> TechnicalAnalysis -> News -> Portfolio
        -> AIAgent -> RiskManager -> Telegram

DRY_RUN_ONLY is enforced in config: this program only ever analyzes
and alerts. No order is ever placed on any exchange.
"""
from __future__ import annotations

import argparse

from config import settings
from core.ai_agent import AIAgent
from core.bitpin_client import BitpinClient
from core.market_data import CoinGeckoProvider, MarketDataRouter, TwelveDataProvider
from core.models import AssetClass
from core.news_analyzer import NewsAnalyzer
from core.opportunity_ranker import OpportunityRanker
from core.risk_manager import RiskLimits, RiskManager
from core.scanner import MarketScanner, WatchlistEntry
from core.scheduler import Scheduler
from core.technical_analysis import TechnicalAnalyzer
from core.telegram_bot import TelegramNotifier
from utils.alert_store import AlertStore
from utils.logger import get_logger


def build_watchlist() -> list[WatchlistEntry]:
    watchlist: list[WatchlistEntry] = []
    watchlist += [WatchlistEntry(s, AssetClass.CRYPTO) for s in settings.watchlist_crypto]
    watchlist += [WatchlistEntry(s, AssetClass.STOCK) for s in settings.watchlist_stocks]
    watchlist += [WatchlistEntry(s, AssetClass.FOREX) for s in settings.watchlist_forex]
    watchlist += [WatchlistEntry(s, AssetClass.GOLD) for s in settings.watchlist_gold]
    return watchlist


def build_scanner(logger) -> MarketScanner:
    if not settings.dry_run_only:
        raise RuntimeError(
            "DRY_RUN_ONLY must stay true — this system is analysis/alert-only for now."
        )

    bitpin = BitpinClient(settings.bitpin_api_key, settings.bitpin_secret_key, settings.bitpin_base_url)

    market_data = MarketDataRouter(
        crypto=CoinGeckoProvider(settings.coingecko_api_key),
        stocks=TwelveDataProvider(settings.twelve_data_api_key),
        forex=TwelveDataProvider(settings.twelve_data_api_key),
        gold=TwelveDataProvider(settings.twelve_data_api_key),
        logger=logger,
    )

    technical_analyzer = TechnicalAnalyzer()
    news_analyzer = NewsAnalyzer(settings.cryptopanic_api_key, settings.news_api_key)
    ai_agent = AIAgent(settings.anthropic_api_key, settings.anthropic_model)

    risk_manager = RiskManager(
        RiskLimits(
            max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
            max_leverage=settings.max_leverage,
            min_liquidation_buffer_mult=settings.min_liquidation_buffer_mult,
            max_portfolio_exposure_pct=settings.max_portfolio_exposure_pct,
        )
    )

    ranker = OpportunityRanker(min_score=settings.min_opportunity_score)
    alert_store = AlertStore(settings.data_dir / "alerts_sent.json", settings.alert_cooldown_hours)
    telegram = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)

    return MarketScanner(
        watchlist=build_watchlist(),
        bitpin_client=bitpin,
        market_data=market_data,
        technical_analyzer=technical_analyzer,
        news_analyzer=news_analyzer,
        ai_agent=ai_agent,
        risk_manager=risk_manager,
        ranker=ranker,
        alert_store=alert_store,
        telegram=telegram,
        timeframe=settings.candle_timeframe,
        candle_lookback=settings.candle_lookback,
        logger=logger,
    )


def main():
    parser = argparse.ArgumentParser(description="AI Autonomous Financial Advisor")
    parser.add_argument("--once", action="store_true", help="Run a single scan cycle and exit.")
    args = parser.parse_args()

    logger = get_logger("advisor", settings.logs_dir)
    logger.info("Booting AI Autonomous Financial Advisor (analysis-only mode).")

    scanner = build_scanner(logger)
    scheduler = Scheduler(scanner, settings.scan_interval_minutes, logger)

    if args.once:
        scheduler.run_once()
    else:
        scheduler.run_forever()


if __name__ == "__main__":
    main()
