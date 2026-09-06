# AI Autonomous Financial Advisor

Autonomous market scanner + Telegram alert bot. Connects to **Bitpin** for
your portfolio/balance and crypto reference prices, scans crypto/stocks/
forex/gold via dedicated market-data APIs, runs technical analysis, checks
news, asks an AI agent to judge the opportunity, and — only if an
**independent, non-AI risk manager** approves it — sends you a single
Telegram alert with exact entry/stop/target/size/leverage.

**No order is ever placed.** `DRY_RUN_ONLY=true` in `.env` is enforced in
code (`main.py` refuses to start otherwise). This is analysis and alerting
only. Nothing here is financial advice — it's a personal research tool.

## Architecture

```
Scheduler ──► MarketScanner ──► TechnicalAnalysis ──► News ──► Portfolio
                                                              │
                                                              ▼
                                                          AIAgent
                                                              │
                                                              ▼
                                                        RiskManager
                                                              │
                                                              ▼
                                                          Telegram
```

Key design rule, enforced structurally (not just by prompting):
**the AI agent's return type has no price/size/leverage field at all.**
Every number a user sees — entry, stop-loss, take-profit, position size,
leverage, margin, liquidation price — comes from `technical_analysis.py`,
`trade_levels.py`, and `risk_manager.py`. The AI only contributes a
direction, a 0-100 conviction score, and a short rationale.

```
financial_advisor/
├── .env.example              # copy to .env and fill in your keys
├── config.py                 # loads & validates all settings
├── main.py                   # entry point (--once for a single test cycle)
├── core/
│   ├── models.py             # shared dataclasses (the contract between stages)
│   ├── bitpin_client.py      # auth + wallet balances + crypto tickers
│   ├── market_data.py        # CoinGecko (crypto) / Twelve Data (stocks, forex, gold)
│   ├── technical_analysis.py # EMA, RSI, MACD, ATR, volume, momentum, S/R, score
│   ├── trade_levels.py       # entry/SL/TP from ATR + support/resistance only
│   ├── news_analyzer.py      # headlines + coarse sentiment (no prices)
│   ├── ai_agent.py           # direction + conviction + rationale ONLY
│   ├── risk_manager.py       # position size, leverage cap, margin, liquidation
│   ├── opportunity_ranker.py # cross-market ranking of approved candidates
│   ├── telegram_bot.py       # formats & sends the final alert
│   └── scanner.py            # orchestrates one full cycle
├── utils/
│   ├── logger.py
│   └── alert_store.py        # cooldown-based duplicate-alert suppression
└── tests/
    ├── test_technical_analysis.py
    ├── test_risk_manager.py
    └── e2e_dry_run.py        # full pipeline with fake network components
```

## Setup

```bash
cd financial_advisor
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: Bitpin keys, Telegram bot token + chat id, Anthropic key, watchlists
```

Run one test cycle (no schedule, exits immediately):
```bash
python main.py --once
```

Run forever (this is what makes it autonomous — put it on a server/VPS
with systemd or `screen`/`tmux`, since it must keep running 24/7 to scan
on its own and message you only when it finds something):
```bash
python main.py
```

## Tests

```bash
python tests/test_technical_analysis.py   # pure indicator math
python tests/test_risk_manager.py         # sizing / leverage / liquidation safety
python tests/e2e_dry_run.py               # full pipeline, no network needed
```

## Notes on the Bitpin integration

The exact REST paths in `core/bitpin_client.py` (`EP_LOGIN`, `EP_WALLETS`,
etc.) are based on published Bitpin client SDKs. They're isolated at the
top of that one file specifically so that if a path is slightly different
on the live API, you only need to fix it in one place — nothing else in
the codebase depends on the exact URL shape.

## Risk model in plain terms

- You set `MAX_RISK_PER_TRADE_PCT` (e.g. 1%) — the most a single stop-loss
  hit can cost you, computed from your real Bitpin free balance.
- You set `MAX_LEVERAGE` (e.g. 3x) — an absolute ceiling the AI cannot
  override.
- The risk manager additionally require the liquidation price sit at least
  `MIN_LIQUIDATION_BUFFER_MULT` × (stop distance) away from entry, and will
  automatically step leverage down (never up) until that's satisfied, or
  reject the trade if even 1x can't satisfy it.
- `MAX_PORTFOLIO_EXPOSURE_PCT` caps how much of your total portfolio value
  a single position's notional can represent.
- Note the arithmetic identity `exposure% = risk_per_trade% / stop_distance%`:
  a very tight stop on a low-volatility asset will naturally require a
  larger position notional to hit your target risk-per-trade — that's why
  the exposure cap exists as a second, independent guardrail.

## Extending

- Add a symbol: add it to the relevant `WATCHLIST_*` in `.env`.
- Add a new asset class or data source: implement `MarketDataProvider`
  in `core/market_data.py` and register it in `main.py`'s `MarketDataRouter`.
- Swap the AI model/provider: `core/ai_agent.py` is a single isolated class.
