# Binance Trading Bot v2.0

Autonomous self-learning trading bot for Binance with Telegram control and web dashboard.

## Features

- **4 Trading Strategies**: Grid, DCA, RSI+EMA, MTF Momentum
- **AutoSelector**: Automatic strategy selection based on market conditions (ADX/RSI)
- **Learning Engine**: Parameter optimization (Optuna), strategy weight learning (SGD), RL agent (PPO)
- **Risk Management**: Max positions, daily loss limit, reserve buffer, cooldown, drawdown breaker
- **Telegram Bot**: 17+ commands for trading, monitoring, and learning control
- **Web Dashboard**: Real-time capital tracking, trade history, strategy metrics, learning status

## Quick Start

### Prerequisites
- Python 3.11+
- Binance Testnet account (API key + secret)
- Telegram Bot Token (from @BotFather)

### Installation

```bash
# Clone repository
git clone https://github.com/VadyaLegolas/binancebot_mimo.git
cd binancebot_mimo

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run bot
python src/main.py
```

### Docker

```bash
docker-compose up -d
```

## Configuration

### Environment Variables (.env)
- `BINANCE_API_KEY` - Binance API key
- `BINANCE_API_SECRET` - Binance API secret
- `BINANCE_TESTNET` - Use testnet (true/false)
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `TELEGRAM_CHAT_ID` - Telegram chat ID for notifications
- `DATABASE_URL` - Database connection string

### Strategy Parameters (config.yaml)
- `strategies.grid` - Grid trading parameters
- `strategies.dca` - DCA parameters
- `strategies.rsi_ema` - RSI+EMA parameters
- `strategies.mtf` - MTF Momentum parameters
- `risk` - Risk management settings

## Telegram Commands

### Trading
- `/init <amount>` - Set starting capital
- `/buy <coin> <amount>` - Buy in USDT
- `/sell <coin> <qty>` - Sell quantity
- `/sell_all <coin>` - Sell all position

### Information
- `/balance` - Account balance
- `/capital` - Capital info
- `/positions` - Open positions
- `/stats` - Trading statistics
- `/pnl` - Profit/Loss summary
- `/price <coin>` - Current price

### Learning
- `/rl on|off|status|train` - RL agent control
- `/learn stats|retrain|history` - Learning engine
- `/strategy auto|grid|dca|rsi_ema|mtf` - Strategy selection

## Architecture

```
src/
├── main.py              # Entry point
├── core/
│   ├── binance_client.py    # Binance API wrapper
│   ├── capital.py           # Capital tracking
│   ├── risk_manager.py      # Risk enforcement
│   ├── pair_manager.py      # Dynamic pair expansion
│   └── ws_manager.py        # WebSocket manager
├── strategies/
│   ├── base.py              # Strategy base class
│   ├── grid.py              # Grid Trading
│   ├── dca.py               # DCA
│   ├── rsi_ema.py           # RSI+EMA
│   ├── mtf.py               # MTF Momentum
│   ├── auto_selector.py     # Strategy routing
│   └── manager.py           # Strategy orchestration
├── learning/
│   ├── parameter_tuner.py   # Optuna optimization
│   ├── strategy_weighter.py # SGD weight learning
│   ├── rl_agent.py          # PPO RL agent
│   ├── trading_env.py       # Gymnasium environment
│   ├── anomaly_guard.py     # Degradation detection
│   └── model_store.py       # Model persistence
├── indicators/
│   └── __init__.py          # RSI, EMA, ADX, ATR
├── database/
│   ├── models.py            # SQLAlchemy models
│   ├── session.py           # DB session
│   └── migrations.py        # Table creation
├── telegram_bot/
│   ├── app.py               # Bot setup
│   └── handlers.py          # Command handlers
└── dashboard/
    ├── app.py               # Flask app
    ├── routes.py            # API endpoints
    └── templates/
        └── index.html       # Dashboard UI
```

## Trading Pairs

- **Core (Day 1)**: BTC, ETH, SOL
- **Extended (50+ trades)**: BNB, XRP, ADA
- **DOGE (100+ wins, Grid only)**: DOGE

## Risk Management

- Max open positions: 7
- Daily loss limit: 5% of capital
- Reserve buffer: 20 USDT
- Cooldown after stop-loss: 15 minutes
- Drawdown breaker: 8% stops all trading

## License

MIT
