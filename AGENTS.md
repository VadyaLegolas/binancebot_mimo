# AGENTS.md

## Project

Binance autonomous trading bot with Telegram control and web dashboard. Python 3.11+. Starts on Testnet, optionally moves to Mainnet.

Spec: `binance_bot_spec_v2.md` (v2 is authoritative over v1).

## Stack

- **API:** `python-binance` or `ccxt`
- **Telegram:** `python-telegram-bot` v20+ (async)
- **Dashboard:** Flask + Chart.js, no auth, localhost only
- **DB:** SQLite (dev) / PostgreSQL (prod), SQLAlchemy
- **ML:** `optuna`, `stable-baselines3`, `scikit-learn`
- **Scheduling:** APScheduler
- **Indicators:** `pandas-ta`, `ta`
- **Deploy:** Docker + docker-compose
- **Config:** `.env` + YAML, never hardcode secrets

## Commands

No code exists yet. Once scaffolded, run:

```bash
# Install
pip install -r requirements.txt

# Run bot
python src/main.py

# Run dashboard
python src/dashboard/app.py  # localhost:5000

# Tests
pytest tests/

# Lint (add when configured)
ruff check src/
```

## Architecture

Entry point: `src/main.py`. Four subsystems run concurrently:
1. **Telegram Bot** — user commands (`/buy BTC 15`, `/sell ETH`, `/balance`, etc.)
2. **Core Engine** — Strategy Manager, Order Manager, Risk Manager, Learning Engine
3. **Web Dashboard** — Flask, Chart.js, no auth
4. **Binance API** — WebSocket data feed + REST orders

## Key Conventions

- All monetary values in **USDT**, not USD or raw crypto amounts
- Telegram commands omit units: `/buy BTC 15` not `/buy BTC 15 USDT`
- Minimum trade: 10-15 USDT (below this, fees eat profit)
- Fee rate: 0.1% per side, 0.2% round-trip. All PnL is **net** of fees
- Symbols in DB use base asset only: `BTC`, `ETH` — not `BTCUSDT`
- Starting capital is fixed at init via `/init <amount>`, stored in `bot_session` table
- Bot tracks: starting capital, realized net PnL, current balance (capital + net PnL)

## Trading Pairs

Core (day 1): BTC, ETH, SOL. Add BNB, XRP, ADA after 50+ trades. DOGE only for Grid, only after 100+ winning trades.

## Learning Engine (v2 only)

Three levels, all optional:
1. **Parameter Tuner** — Optuna optimizes strategy params every 50 trades
2. **Strategy Weighter** — SGD classifier updates strategy weights every 4 hours
3. **RL Agent** — PPO via stable-baselines3, shadow mode by default, live via `/rl on`

Anomaly Guard watches for degradation: rollback if win rate < 40% over 20 trades, stop if drawdown > 8%.

## Gotchas

- `MIN_NOTIONAL` filter must be checked via API before every order
- Grid step minimum 0.5% to cover round-trip fees
- RL agent has three modes: training (offline), shadow (observe only), live (trades). Default is shadow
- Walk-forward validation: train on 80% data, test on 20%. Never skip this
- Dashboard has no password — localhost/SSH only
