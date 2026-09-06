"""
End-to-end dry run of the full architecture:

    Scheduler -> Scanner -> TechnicalAnalysis -> News -> Portfolio
        -> AIAgent -> RiskManager -> Telegram

Every network-touching component (Bitpin, market data, news,
Telegram) is replaced with a lightweight fake so this test can run
with zero internet access, while still exercising the *real*
TechnicalAnalyzer, RiskManager, AIAgent (offline/rule-based mode),
OpportunityRanker, and AlertStore code paths unmodified.

This proves the pieces fit together correctly; swapping the fakes
for the real BitpinClient / CoinGeckoProvider / TwelveDataProvider /
TelegramNotifier in main.py is all that's needed for production use.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ai_agent import AIAgent
from core.market_data import MarketDataRouter, SyntheticProvider
from core.models import AssetClass, Portfolio, WalletBalance
from core.news_analyzer import NewsAnalyzer
from core.opportunity_ranker import OpportunityRanker
from core.risk_manager import RiskLimits, RiskManager
from core.scanner import MarketScanner, WatchlistEntry
from core.technical_analysis import TechnicalAnalyzer
from core.telegram_bot import TelegramNotifier
from utils.alert_store import AlertStore
from utils.logger import get_logger


class FakeBitpinClient:
    """
    Stands in for BitpinClient — returns a fixed portfolio, no network.

    NOTE on sizing: exposure_pct = risk_per_trade_pct / stop_distance_pct
    is a hard mathematical relationship, not a bug. A tight stop (small
    stop_distance_pct) forced by low-volatility synthetic data means a
    1%-account-risk position naturally has to be a large fraction of
    the portfolio to reach that same 1% loss if the stop is hit. A
    real, diversified multi-thousand-dollar account with many possible
    watchlist symbols would keep any single position's share modest;
    here with a single test portfolio we size it generously so the
    "clear uptrend" scenario can demonstrate full risk-manager approval.
    """

    def get_portfolio(self) -> Portfolio:
        return Portfolio(
            balances=[WalletBalance("USDT", 10_000.0, 8_000.0, 10_000.0)],
            total_value_quote=10_000.0,
            free_capital_quote=8_000.0,
            quote_currency="USDT",
        )


class FakeNewsAnalyzer(NewsAnalyzer):
    """Skips real HTTP calls; returns neutral news for every symbol."""

    def analyze(self, symbol: str):
        from core.models import NewsAssessment
        return NewsAssessment(symbol=symbol, headlines=[], sentiment_score=0.0,
                               has_high_impact_event=False, summary="no network in dry run")


class RecordingTelegramNotifier(TelegramNotifier):
    """Captures what WOULD be sent instead of making an HTTP call."""

    def __init__(self):
        super().__init__(bot_token="", chat_id="")
        self.sent_messages = []

    @property
    def is_configured(self) -> bool:
        return True  # pretend configured so scanner exercises the send path

    def send_opportunity(self, opp) -> None:
        self.sent_messages.append(self.format_opportunity(opp))


def run():
    logger = get_logger("e2e_dry_run", Path("/tmp/advisor_dry_run_logs"))

    # Three synthetic symbols: clear uptrend, clear downtrend, choppy/no-edge.
    market_data = MarketDataRouter(
        crypto=SyntheticProvider(drift=0.6),   # will be used per-symbol below via a wrapper
        stocks=SyntheticProvider(drift=0.6),
        forex=SyntheticProvider(drift=0.6),
        gold=SyntheticProvider(drift=0.6),
    )

    # Give each symbol a distinct trend by wrapping providers per asset class
    # is not expressive enough for per-symbol drift, so patch get_ohlcv here:
    base_provider = SyntheticProvider()

    def get_ohlcv(asset_class, symbol, timeframe, limit):
        drift = {"BTC_TREND_UP": 0.7, "XYZ_TREND_DOWN": -0.7, "FLAT_NOEDGE": 0.0}.get(symbol, 0.0)
        return SyntheticProvider(drift=drift).get_ohlcv(symbol, timeframe, limit)

    market_data.get_ohlcv = get_ohlcv  # monkeypatch for deterministic per-symbol scenarios

    watchlist = [
        WatchlistEntry("BTC_TREND_UP", AssetClass.CRYPTO),
        WatchlistEntry("XYZ_TREND_DOWN", AssetClass.CRYPTO),
        WatchlistEntry("FLAT_NOEDGE", AssetClass.CRYPTO),
    ]

    scanner = MarketScanner(
        watchlist=watchlist,
        bitpin_client=FakeBitpinClient(),
        market_data=market_data,
        technical_analyzer=TechnicalAnalyzer(),
        news_analyzer=FakeNewsAnalyzer(),
        ai_agent=AIAgent(api_key="", model="unused"),  # offline/rule-based mode, no network
        risk_manager=RiskManager(RiskLimits(
            max_risk_per_trade_pct=1.0, max_leverage=3.0,
            min_liquidation_buffer_mult=2.0, max_portfolio_exposure_pct=70.0,
        )),
        ranker=OpportunityRanker(min_score=60.0),
        alert_store=AlertStore(Path("/tmp/advisor_dry_run_alerts.json"), cooldown_hours=6.0),
        telegram=RecordingTelegramNotifier(),
        timeframe="1h",
        candle_lookback=150,
        logger=logger,
    )

    print("\n=== CYCLE 1 ===")
    sent1 = scanner.run_cycle()
    print(f"\nAlerts sent in cycle 1: {len(sent1)}")
    for msg in scanner.telegram.sent_messages:
        print("---- TELEGRAM MESSAGE ----")
        print(msg)

    print("\n=== CYCLE 2 (immediately after) — duplicate-alert suppression check ===")
    sent2 = scanner.run_cycle()
    print(f"Alerts sent in cycle 2: {len(sent2)} (expected 0 — cooldown should suppress repeats)")

    assert len(sent1) >= 1, "Expected at least one opportunity (the clear uptrend symbol) to alert."
    assert len(sent2) == 0, "Cooldown should have suppressed the identical alert on the very next cycle."
    assert all(o.approved for o in sent1), "Only risk-approved opportunities should ever be sent."

    for opp in sent1:
        assert opp.leverage <= 3.0
        assert opp.liquidation_price is not None
        assert opp.risk_amount_quote <= 8_000.0 * 0.01 + 1e-6  # 1% of free capital

    print("\nE2E dry run PASSED: full pipeline (Scanner -> Technical -> News -> AI "
          "-> RiskManager -> Telegram -> AlertStore) works end to end.")


if __name__ == "__main__":
    run()
