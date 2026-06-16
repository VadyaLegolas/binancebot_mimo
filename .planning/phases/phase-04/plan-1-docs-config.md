---
wave: 1
depends_on: []
files_modified:
  - README.md
  - .env.example
  - config.yaml
  - docker-compose.yml
  - Dockerfile
requirements_addressed: []
autonomous: true
---

# Plan 1 — Documentation + Config Hardening

<objective>
Create comprehensive documentation (README.md), harden configuration with validation, and prepare production-ready Docker setup. By end of this plan: README explains setup/usage/architecture, config validates on startup, Docker works with env vars.
</objective>

---

## Task 1.1 — Create README.md

<read_first>
- binance_bot_spec_v2.md (project overview)
- .planning/ROADMAP.md (phases and requirements)
- AGENTS.md (project conventions)
- requirements.txt (dependencies)
</read_first>

<action>
1. Write `README.md`:

```markdown
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
```
</action>

<acceptance_criteria>
- README.md exists and is valid markdown
- Covers: features, quick start, configuration, commands, architecture
- All sections present and accurate
</acceptance_criteria>

---

## Task 1.2 — Harden config.yaml with validation

<read_first>
- config.yaml (current content)
- src/main.py (load_config function)
</read_first>

<action>
1. Add config validation to `src/main.py`:

```python
def load_config() -> dict:
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    
    # Validate required sections
    required = ["starting_capital", "capital", "fees", "trading_pairs", "strategies"]
    for section in required:
        if section not in config:
            raise ValueError(f"Missing config section: {section}")
    
    # Validate strategy params
    for strat in ["grid", "dca", "rsi_ema", "mtf"]:
        if strat not in config.get("strategies", {}):
            raise ValueError(f"Missing strategy config: {strat}")
    
    # Validate risk params
    risk = config.get("risk", {})
    if risk.get("max_open_positions", 0) < 1:
        raise ValueError("max_open_positions must be >= 1")
    if risk.get("daily_loss_limit_pct", 0) <= 0:
        raise ValueError("daily_loss_limit_pct must be > 0")
    
    return config
```

2. Add startup validation message:

```python
def main():
    logger.info("Starting Binance Trading Bot...")
    
    config = load_config()
    logger.info(f"Config loaded: {len(config.get('strategies', {}))} strategies")
```
</action>

<acceptance_criteria>
- load_config validates required sections
- load_config validates strategy configs
- load_config validates risk params
- Clear error messages on missing/invalid config
</acceptance_criteria>

---

## Task 1.3 — Update .env.example with all variables

<read_first>
- .env.example (current content)
</read_first>

<action>
1. Update `.env.example`:

```bash
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true

# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ADMIN_IDS=123456789

# Database
DATABASE_URL=sqlite:///data/trading_bot.db

# Dashboard
FLASK_HOST=0.0.0.0
FLASK_PORT=5000

# Logging
LOG_LEVEL=INFO
```
</action>

<acceptance_criteria>
- .env.example contains all required variables
- Comments explain each variable
</acceptance_criteria>

---

## Artifacts this plan produces

| File | Purpose |
|------|---------|
| `README.md` | Comprehensive project documentation |
| `src/main.py` | Config validation on startup |
| `.env.example` | Updated environment template |
