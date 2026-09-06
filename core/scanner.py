"""
MarketScanner — one full pass of:

  Portfolio -> for each symbol: MarketData -> TechnicalAnalysis -> News
    -> AIAgent -> TradeLevels -> RiskManager -> Opportunity

then OpportunityRanker picks the best of the batch, AlertStore filters
out repeats, and TelegramNotifier sends only what's left. If nothing
qualifies, nothing is sent — silence is a valid, expected outcome.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from core.ai_agent import AIAgent
from core.bitpin_client import BitpinClient
from core.market_data import MarketDataRouter
from core.models import AssetClass, Direction, Opportunity, Portfolio
from core.news_analyzer import NewsAnalyzer
from core.opportunity_ranker import OpportunityRanker, compute_composite_score
from core.risk_manager import RiskManager
from core.technical_analysis import TechnicalAnalyzer
from core.telegram_bot import TelegramNotifier
from core.trade_levels import compute_levels
from utils.alert_store import AlertStore


@dataclass
class WatchlistEntry:
    symbol: str
    asset_class: AssetClass


class MarketScanner:
    def __init__(
        self,
        watchlist: List[WatchlistEntry],
        bitpin_client: BitpinClient,
        market_data: MarketDataRouter,
        technical_analyzer: TechnicalAnalyzer,
        news_analyzer: NewsAnalyzer,
        ai_agent: AIAgent,
        risk_manager: RiskManager,
        ranker: OpportunityRanker,
        alert_store: AlertStore,
        telegram: TelegramNotifier,
        timeframe: str,
        candle_lookback: int,
        logger: logging.Logger,
    ):
        self.watchlist = watchlist
        self.bitpin_client = bitpin_client
        self.market_data = market_data
        self.technical_analyzer = technical_analyzer
        self.news_analyzer = news_analyzer
        self.ai_agent = ai_agent
        self.risk_manager = risk_manager
        self.ranker = ranker
        self.alert_store = alert_store
        self.telegram = telegram
        self.timeframe = timeframe
        self.candle_lookback = candle_lookback
        self.logger = logger

    def _get_portfolio(self) -> Portfolio:
        try:
            return self.bitpin_client.get_portfolio()
        except Exception as exc:
            self.logger.error(f"Failed to fetch portfolio from Bitpin: {exc}")
            return Portfolio()  # empty/zero portfolio -> risk manager will reject everything safely

    def _evaluate_symbol(self, entry: WatchlistEntry, portfolio: Portfolio) -> Opportunity | None:
        try:
            candles = self.market_data.get_ohlcv(
                entry.asset_class.value, entry.symbol, self.timeframe, self.candle_lookback
            )
            technical = self.technical_analyzer.analyze(entry.symbol, entry.asset_class, candles)
        except Exception as exc:
            self.logger.warning(f"[{entry.symbol}] technical analysis failed, skipping: {exc}")
            return None

        if technical.bias == Direction.NONE:
            return None  # no meaningful edge, skip AI/news calls entirely to save quota

        try:
            news = self.news_analyzer.analyze(entry.symbol)
        except Exception as exc:
            self.logger.warning(f"[{entry.symbol}] news fetch failed, continuing without news: {exc}")
            from core.models import NewsAssessment
            news = NewsAssessment(symbol=entry.symbol)

        ai_assessment = self.ai_agent.assess(technical, news)
        if ai_assessment.direction == Direction.NONE or ai_assessment.conviction <= 0:
            return None

        # Direction must agree between technical bias and AI judgement —
        # if they disagree, treat it as insufficient conviction rather
        # than trusting either side blindly.
        if ai_assessment.direction != technical.bias:
            return None

        entry_price, stop_loss, take_profit = compute_levels(technical, ai_assessment.direction)

        current_exposure = next(
            (b.value_in_quote for b in portfolio.balances if b.currency == entry.symbol.split("_")[0]),
            0.0,
        )
        decision = self.risk_manager.evaluate(
            direction=ai_assessment.direction,
            entry=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            proposed_leverage=self.risk_manager.limits.max_leverage,
            portfolio=portfolio,
            symbol_current_exposure_quote=current_exposure,
        )

        composite = compute_composite_score(technical.score, ai_assessment.conviction)

        opp = Opportunity(
            symbol=entry.symbol,
            asset_class=entry.asset_class,
            direction=ai_assessment.direction,
            technical=technical,
            news=news,
            ai=ai_assessment,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            composite_score=composite,
            leverage=decision.leverage,
            position_size=decision.position_size,
            position_value_quote=decision.position_value_quote,
            margin_required=decision.margin_required,
            liquidation_price=decision.liquidation_price,
            liquidation_distance_pct=decision.liquidation_distance_pct,
            risk_amount_quote=decision.risk_amount_quote,
            approved=decision.approved,
            rejection_reason=decision.reason,
        )
        return opp

    def run_cycle(self) -> List[Opportunity]:
        self.logger.info(f"Starting scan cycle over {len(self.watchlist)} symbols...")
        portfolio = self._get_portfolio()

        candidates: List[Opportunity] = []
        for entry in self.watchlist:
            opp = self._evaluate_symbol(entry, portfolio)
            if opp is not None:
                status = "APPROVED" if opp.approved else f"REJECTED ({opp.rejection_reason})"
                self.logger.info(
                    f"[{entry.symbol}] direction={opp.direction.value} "
                    f"score={opp.composite_score:.1f} -> {status}"
                )
                candidates.append(opp)

        top = self.ranker.rank(candidates)
        if not top:
            self.logger.info("No qualifying opportunity this cycle — no alert sent.")
            return []

        sent: List[Opportunity] = []
        for opp in top:
            if not self.alert_store.should_alert(opp.symbol, opp.direction.value):
                self.logger.info(f"[{opp.symbol}] suppressed — alerted within cooldown window.")
                continue
            if self.telegram.is_configured:
                self.telegram.send_opportunity(opp)
            else:
                self.logger.warning("Telegram not configured — opportunity computed but not sent:")
                self.logger.warning(self.telegram.format_opportunity(opp))
            self.alert_store.mark_sent(opp.symbol, opp.direction.value)
            sent.append(opp)

        return sent
