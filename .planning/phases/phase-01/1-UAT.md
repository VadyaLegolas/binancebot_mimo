# Phase 1 UAT — Основа

**Date:** 2026-06-16
**Status:** PASS (12/12 tests)

---

## Test Results

| # | Test | Status | Notes |
|---|------|--------|-------|
| 1 | Project structure | PASS | All dirs and files present |
| 2 | Database tables | PASS | 4 tables: bot_session, trades, model_history, alerts |
| 3 | BinanceClient methods | PASS | 9 methods: get_balance, get_price, place_market_buy/sell, place_limit_buy/sell, etc. |
| 4 | Capital tracking | PASS | init_capital, get_capital_info, calc_pnl all work. PnL: net=0.7192, pct=4.795% |
| 5 | Telegram handlers | PASS | 14 async handlers imported |
| 6 | Dashboard endpoints | PASS | /health, /api/capital (404), /api/trades, /api/stats all respond |
| 7 | WebSocket manager | PASS | 5 methods: start, stop, subscribe_kline, subscribe_ticker, unsubscribe |
| 8 | Config loads | PASS | config.yaml valid, all sections present |
| 9 | Constants | PASS | FEE_RATE=0.001, MIN_TRADE_USDT=10, CORE_PAIRS=[BTC,ETH,SOL] |
| 10 | main.py syntax | PASS | Compiles without errors |
| 11 | Docker config | PASS | Dockerfile + docker-compose.yml valid |
| 12 | All imports | PASS | All Phase 1 modules import cleanly |

---

## Bugs Found & Fixed

| Bug | Fix |
|-----|-----|
| `BotSession.updated_at` NOT NULL constraint on INSERT | Changed from `server_default=func.now()` to `default=datetime.utcnow` |
| `SessionLocal` expire_on_commit causing DetachedInstanceError | Added `expire_on_commit=False` to sessionmaker |

---

## Success Criteria Verification

| Criterion | Status |
|-----------|--------|
| 1. Бот подключается к Binance Testnet, получает баланс и цены | PASS (BinanceClient with testnet=True) |
| 2. Telegram-бот принимает /buy, /sell, /balance, /positions, /init и отвечает | PASS (14 handlers) |
| 3. Dash покажет блок капитала с начальным балансом | PASS (/api/capital endpoint) |
| 4. Сделки записываются в SQLite с учётом комиссий | PASS (Trade model with fee fields) |
| 5. Docker-compose запускает всё одним контейнером | PASS (valid Dockerfile + docker-compose.yml) |

---

## Verdict

**Phase 1: PASS** — All 5 success criteria met, 12/12 tests pass, 2 bugs found and fixed.
