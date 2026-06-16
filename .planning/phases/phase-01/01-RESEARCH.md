# RESEARCH.md — Phase 1: Foundation

**Phase:** 1 — Основа (Foundation)
**Date:** 2026-06-16
**Goal:** Working scaffold with Binance API, Telegram bot, dashboard and DB — ready for adding strategies

---

## Standard Stack

| Library | Version | Rationale |
|---------|---------|-----------|
| `python-binance` | **1.0.37** | Latest (Jun 2026). Native Testnet support via `testnet=True`. Async client (`AsyncClient`), `ThreadedWebsocketManager` for live data. [VERIFIED: pypi.org/project/python-binance] |
| `python-telegram-bot` | **22.8** | Latest (Jun 2026). Fully async since v20. Requires Python ≥3.10. Optional `[job-queue]` extra installs APScheduler for scheduled tasks. [VERIFIED: pypi.org/project/python-telegram-bot] |
| `Flask` | **3.1.3** | Latest (Feb 2026). WSGI, Jinja2, lightweight. `[dotenv]` extra for .env loading. [VERIFIED: pypi.org/project/Flask] |
| `Flask-SQLAlchemy` | **3.1.1** | Flask integration for SQLAlchemy. Simplifies session management per-request. [ASSUMED: compatible with Flask 3.x] |
| `SQLAlchemy` | **2.0.51** | Latest (Jun 2026). Use `DeclarativeBase` + `mapped_column` (2.0 style). Sync sessions for SQLite. [VERIFIED: pypi.org/project/SQLAlchemy] |
| `APScheduler` | **3.10.4** | Required by python-telegram-bot `[job-queue]` extra (constrained `>=3.10.4,<3.12.0`). Use `BackgroundScheduler` for non-Telegram scheduled jobs. [VERIFIED: python-telegram-bot deps] |
| `Loguru` | **0.7.2** | Spec-listed. Drop-in replacement for stdlib logging. Rotating file + stdout. |
| `python-dotenv` | **1.0.0** | Load `.env` into `os.environ`. Used by Flask `[dotenv]` and direct. |
| `PyYAML` | **6.0.1** | Load `config.yaml` strategy parameters. |
| `pandas` | **2.1.4** | Spec-listed. Required for indicators (pandas-ta) and data processing. |
| `numpy` | **1.26.2** | Pandas dependency, used for calculations. |

**Do NOT install in Phase 1** (Phase 2/3 deps): `pandas-ta`, `ta`, `scikit-learn`, `optuna`, `stable-baselines3`, `gymnasium`, `backtesting`.

---

## Architecture Patterns

### 1. Async vs Sync Split

**Critical decision:** The system has two async subsystems (Telegram bot, Binance WebSocket) and two sync subsystems (Flask dashboard, SQLite DB). Use a hybrid architecture:

```
main.py (asyncio event loop)
├── Telegram Bot (python-telegram-bot, async, runs via Application.run_polling())
├── Binance Client (python-binance sync Client for REST orders)
├── Binance WebSocket (ThreadedWebsocketManager, runs in background thread)
├── Flask Dashboard (sync WSGI, runs in background thread)
└── APScheduler (BackgroundScheduler, runs in background thread)
```

**Use `Client` (sync)** for REST API calls (orders, balance, klines). The sync client is simpler and sufficient for Phase 1 — orders are not latency-critical on Testnet.

**Use `AsyncClient`** only if you need concurrent REST calls. Not needed in Phase 1.

**Use `ThreadedWebsocketManager`** for WebSocket kline/price streams. It handles reconnection automatically and runs in its own thread.

**Use `Application.run_polling()`** for Telegram. It manages its own asyncio loop. Do NOT start a separate event loop.

### 2. Component Boundaries

```
src/
├── main.py                  # Entry point: wires everything together
├── core/
│   ├── binance_client.py    # Wrapper around python-binance (REST)
│   ├── ws_manager.py        # ThreadedWebsocketManager wrapper
│   ├── capital.py           # Capital tracking: starting, net_pnl, balance
│   └── constants.py         # FEE_RATE, MIN_TRADE_USDT, etc.
├── database/
│   ├── models.py            # SQLAlchemy ORM models
│   ├── session.py           # Engine + SessionLocal factory
│   └── migrations.py        # DDL creation (CREATE TABLE IF NOT EXISTS)
├── telegram_bot/
│   ├── app.py               # Application setup, handler registration
│   └── handlers.py          # /buy, /sell, /balance, /init, etc.
├── dashboard/
│   ├── app.py               # Flask app + blueprints
│   ├── routes.py            # /, /api/capital, /api/trades
│   └── templates/
│       └── index.html       # Jinja2 + Chart.js
├── strategies/              # Empty in Phase 1, placeholder
│   └── __init__.py
├── indicators/              # Empty in Phase 1
│   └── __init__.py
└── learning/                # Empty in Phase 1
    └── __init__.py
```

### 3. Data Flow

```
Binance WebSocket → ws_manager.py → stores latest prices in memory (dict)
Binance REST     → binance_client.py → orders, balance, klines
Telegram Bot     → handlers.py → calls binance_client → records to DB
Flask Dashboard  → reads DB → renders templates / JSON API
APScheduler      → (Phase 2: strategy ticks)
```

### 4. Database Session Pattern

Use `flask-sqlalchemy` for the Flask app (per-request sessions). For the Telegram bot and other async code, create a standalone `SessionLocal` factory:

```python
# database/session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///trading_bot.db"))
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### 5. Telegram → DB Bridge

Telegram handlers call business logic that uses `SessionLocal()` directly (not Flask's `db.session`). This keeps the Telegram bot decoupled from Flask.

---

## Don't Hand-Roll

| What | Use Instead |
|------|-------------|
| HTTP client for Binance | `python-binance` `Client` — handles signing, timestamps, recvWindow, rate limits |
| WebSocket management | `ThreadedWebsocketManager` — handles reconnection, multiplexing |
| Database ORM | SQLAlchemy `DeclarativeBase` — models as Python classes |
| Schema migrations | For Phase 1: `CREATE TABLE IF NOT EXISTS` in `migrations.py`. Add Alembic in Phase 2 if needed. |
| Config loading | `python-dotenv` for secrets, `PyYAML` for params |
| Logging | `Loguru` — `logger.info()`, `logger.error()` with rotation |
| Scheduled tasks | `APScheduler` `BackgroundScheduler` — interval/cron triggers |
| Telegram bot framework | `python-telegram-bot` `Application` + `CommandHandler` |
| Chart.js | CDN link: `https://cdn.jsdelivr.net/npm/chart.js` |

---

## Common Pitfalls

### python-binance

1. **Testnet URL**: Pass `testnet=True` to `Client()`. Do NOT hardcode testnet URLs — the library handles it. [CITED: python-binance docs]
2. **Symbol format**: REST API uses `BTCUSDT`, but DB stores `BTC` (base asset only). Always convert: `symbol + "USDT"` for API calls, `symbol.replace("USDT", "")` for DB.
3. **MIN_NOTIONAL filter**: Call `client.get_symbol_info(symbol)["filters"]` and check `MIN_NOTIONAL` before EVERY order. Filters change per symbol. Cache for the session but re-check periodically.
4. **Rate limits**: Binance Spot: 1200 requests/min weight. `get_symbol_info` is weight 40. Don't poll it in a tight loop.
5. **Order quantity precision**: Each symbol has `stepSize` and `minQty` filters. Use `client.quantity_precision(symbol)` and `client.price_precision(symbol)` to round correctly. **This is the #1 source of order rejections.**
6. **ThreadedWebsocketManager**: Must call `twm.start()` before subscribing. Must call `twm.stop()` on shutdown. Kline callbacks receive dicts with `k` field containing OHLCV.
7. **Exception handling**: Wrap all API calls in `try/except BinanceAPIException`. Common errors: `-1013` (filters), `-1021` (timestamp), `-2010` (insufficient balance).

### python-telegram-bot

1. **v20+ is fully async**: All handlers must be `async def`. Use `await` for API calls. Do NOT use sync `bot.send_message()` — use `await context.bot.send_message()`. [CITED: python-telegram-bot docs]
2. **Application.run_polling() blocks**: It runs the asyncio event loop. Do NOT try to start Flask or other async code in the same thread. Run Flask in a separate thread.
3. **Handler arguments**: Command handlers receive `(update, context)`. Parse args from `context.args` (list of strings). Example: `/buy BTC 15` → `context.args = ["BTC", "15"]`.
4. **No thread safety**: python-telegram-bot is NOT thread-safe. Do not share `Application` instance across threads. If you need to send messages from Flask/APScheduler threads, use `asyncio.run_coroutine_threadsafe()` with the bot's event loop.
5. **JobQueue dependency**: Install with `pip install "python-telegram-bot[job-queue]"` to get APScheduler integration for periodic tasks (e.g., daily reports).
6. **Error handling**: Use `Application.add_error_handler()` for unhandled exceptions in handlers.

### Flask Dashboard

1. **Thread safety**: Flask's `g` object and `request` context are per-thread. Do NOT share them outside request handlers.
2. **Database sessions**: Use `db.session` within request handlers only. For background threads, use `SessionLocal()`.
3. **CORS**: Not needed — dashboard is localhost-only. If you add CORS later, use `flask-cors`.
4. **Static files**: Put Chart.js CDN in `index.html`. For production, vendor it to `static/vendor/chart.js`.
5. **JSON API pattern**: Use `@bp.route("/api/capital")` returning `jsonify(data)` for frontend chart consumption.
6. **Template caching**: Flask caches Jinja2 templates in production. Set `TEMPLATES_AUTO_RELOAD=True` in development.

### SQLAlchemy

1. **2.0 style**: Use `class Base(DeclarativeBase): pass` and `mapped_column()` instead of old `Column()`. [CITED: SQLAlchemy 2.0 migration guide]
2. **Session management**: Never leave sessions open. Use `sessionmaker` + context manager or `try/finally` with `session.close()`.
3. **SQLite limitations**: SQLite does not support `ALTER TABLE` well. Use `CREATE TABLE IF NOT EXISTS` for Phase 1. Add Alembic for schema evolution later.
4. **Float precision for money**: Use `REAL` (float) for USDT amounts in SQLite. For PostgreSQL in production, consider `Numeric(12,4)`. SQLite has no `Numeric` type — `REAL` is fine for this project's scale.
5. **relationship lazy loading**: Default is `lazy="select"`. For dashboard queries that need related data, use `lazy="joined"` or explicit `joinedload()`.

### Docker

1. **Multi-stage build**: Use `python:3.11-slim` as base. Copy `requirements.txt` first for layer caching.
2. **SQLite in Docker**: Mount a volume for the `.db` file, or it will be lost on container restart. Use `/data/trading_bot.db`.
3. **Single process**: Docker-compose with one service for the bot. Flask and Telegram run as threads inside the same Python process.
4. **Health check**: Add a simple health endpoint to Flask: `GET /health` → `{"status": "ok"}`.
5. **Environment variables**: Pass `.env` file via `env_file:` in docker-compose, NOT via `environment:` (secrets leak in `docker inspect`).

### APScheduler

1. **BackgroundScheduler**: Use `BackgroundScheduler` (thread-based), NOT `AsyncIOScheduler` (incompatible with python-telegram-bot's loop).
2. **Job stores**: Use default `MemoryJobStore`. Do NOT use `SQLAlchemyJobStore` in Phase 1 — adds complexity without benefit.
3. **Misfire handling**: Set `misfire_grace_time=60` to avoid missed jobs if the system was busy.
4. **Shutdown**: Call `scheduler.shutdown()` on app exit to prevent orphan threads.

---

## Code Patterns

### Binance Client Wrapper

```python
# core/binance_client.py
from binance.client import Client
from binance.exceptions import BinanceAPIException
from loguru import logger

class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.testnet = testnet

    def get_balance(self, asset: str = "USDT") -> float:
        account = self.client.get_account()
        for balance in account["balances"]:
            if balance["asset"] == asset:
                return float(balance["free"])
        return 0.0

    def get_price(self, symbol: str) -> float:
        ticker = self.client.get_symbol_ticker(symbol=f"{symbol}USDT")
        return float(ticker["price"])

    def get_min_notional(self, symbol: str) -> float:
        info = self.client.get_symbol_info(f"{symbol}USDT")
        for f in info["filters"]:
            if f["filterType"] == "NOTIONAL":
                return float(f["minNotional"])
        return 10.0  # default fallback

    def place_market_buy(self, symbol: str, quote_qty: float) -> dict:
        return self.client.create_order(
            symbol=f"{symbol}USDT",
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            quoteOrderQty=quote_qty,
        )
```

### Telegram Bot Setup

```python
# telegram_bot/app.py
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram import Update

def create_app(token: str) -> Application:
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("init", handle_init))
    app.add_handler(CommandHandler("buy", handle_buy))
    app.add_handler(CommandHandler("balance", handle_balance))
    # ... register all handlers
    return app

async def handle_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /init <amount>")
        return
    amount = float(context.args[0])
    # ... save to DB, reply confirmation
    await update.message.reply_text(f"Starting capital: {amount:.2f} USDT")

async def handle_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /buy BTC 15
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /buy <coin> <amount_usdt>")
        return
    symbol = context.args[0].upper()
    amount = float(context.args[1])
    # ... execute trade, reply result
```

### Flask Dashboard with Chart.js

```python
# dashboard/app.py
from flask import Flask, render_template, jsonify
from database.session import get_db
from database.models import BotSession, Trade

bp = Flask(__name__, template_folder="templates")

@bp.route("/")
def index():
    return render_template("index.html")

@bp.route("/api/capital")
def api_capital():
    db = next(get_db())
    session = db.query(BotSession).order_by(-BotSession.id).first()
    if not session:
        return jsonify({"error": "No session found"}), 404
    # Calculate capital info per spec §9.2
    net_pnl = db.query(func.sum(Trade.net_pnl)).filter(
        Trade.status == "CLOSED"
    ).scalar() or 0.0
    return jsonify({
        "starting_capital": session.starting_capital,
        "net_pnl": net_pnl,
        "current_balance": session.starting_capital + net_pnl,
    })
```

```html
<!-- dashboard/templates/index.html -->
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div id="capital-block"></div>
    <canvas id="balanceChart"></canvas>
    <script>
        fetch("/api/capital")
            .then(r => r.json())
            .then(data => {
                document.getElementById("capital-block").innerHTML = `
                    <p>Starting: ${data.starting_capital} USDT</p>
                    <p>Net PnL: ${data.net_pnl} USDT</p>
                    <p>Balance: ${data.current_balance} USDT</p>
                `;
            });
        // Chart.js balance line chart...
    </script>
</body>
</html>
```

### SQLAlchemy Models (2.0 style)

```python
# database/models.py
from sqlalchemy import String, Float, Integer, DateTime, Boolean, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class BotSession(Base):
    __tablename__ = "bot_session"
    id: Mapped[int] = mapped_column(primary_key=True)
    starting_capital: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    max_balance: Mapped[float] = mapped_column(Float, default=0.0)
    current_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, onupdate=func.now())

class Trade(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    strategy: Mapped[str] = mapped_column(String(20), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    total_usdt: Mapped[float] = mapped_column(Float, nullable=False)
    fee_rate: Mapped[float] = mapped_column(Float, default=0.001)
    fee_buy: Mapped[float] = mapped_column(Float, default=0.0)
    fee_sell: Mapped[float] = mapped_column(Float, default=0.0)
    fee_total: Mapped[float] = mapped_column(Float, default=0.0)
    gross_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    opened_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    closed_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
```

### Docker Setup

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 5000
CMD ["python", "src/main.py"]
```

```yaml
# docker-compose.yml
services:
  bot:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data
    ports:
      - "5000:5000"
    restart: unless-stopped
```

### Main Entry Point

```python
# src/main.py
import threading
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

def run_flask():
    from dashboard.app import create_app
    app = create_app()
    app.run(host="0.0.0.0", port=5000, use_reloader=False)

def main():
    logger.info("Starting Binance Trading Bot...")

    # Start Flask in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start Telegram bot (blocks — runs asyncio loop)
    from telegram_bot.app import create_app
    from core.binance_client import BinanceClient
    import os

    binance = BinanceClient(
        os.getenv("BINANCE_API_KEY"),
        os.getenv("BINANCE_API_SECRET"),
        testnet=os.getenv("BINANCE_TESTNET", "true") == "true",
    )

    tg_app = create_app(
        token=os.getenv("TELEGRAM_BOT_TOKEN"),
        binance=binance,
    )
    tg_app.run_polling()  # Blocks here

if __name__ == "__main__":
    main()
```

---

## Validation Architecture

### Component Tests

| Component | How to Test | Pass Criteria |
|-----------|-------------|---------------|
| **Binance connection** | `python -c "from binance.client import Client; c = Client(key, secret, testnet=True); print(c.get_account())"` | Returns account dict with balances |
| **Binance price feed** | `c.get_symbol_ticker(symbol='BTCUSDT')` | Returns `{'symbol': 'BTCUSDT', 'price': '...'}` |
| **Binance order** | `c.create_test_order(symbol='BTCUSDT', side='BUY', type='MARKET', quoteOrderQty=15)` | Returns order dict (test order, no real fill) |
| **MIN_NOTIONAL check** | `c.get_symbol_info('BTCUSDT')['filters']` → find NOTIONAL filter | Returns min notional value |
| **Telegram bot** | Send `/init 100` in Telegram → bot replies with confirmation | Reply contains "100.00 USDT" |
| **Telegram /balance** | Send `/balance` → bot shows account balance | Reply shows USDT balance |
| **SQLite tables** | `python -c "from database.models import Base; from database.session import engine; Base.metadata.create_all(engine)"` | Tables created without error |
| **Flask dashboard** | `curl http://localhost:5000/` | Returns HTML with capital block |
| **Flask API** | `curl http://localhost:5000/api/capital` | Returns JSON with starting_capital, net_pnl, current_balance |
| **Docker build** | `docker-compose build` | Image builds successfully |
| **Docker run** | `docker-compose up` | Bot starts, connects to Telegram, Flask serves on :5000 |
| **Loguru logging** | Check `logs/` directory and stdout | Log files created, entries written |
| **Capital tracking** | `/init 100` → `/balance` → verify starting_capital=100, net_pnl=0, balance=100 | Correct three-value display |

### Integration Test Flow

```
1. Bot starts → connects to Binance Testnet ✓
2. Bot starts → connects to Telegram ✓
3. Bot starts → Flask serves on :5000 ✓
4. /init 100 → DB has bot_session with starting_capital=100 ✓
5. /balance → shows 100.00 USDT ✓
6. /buy BTC 15 → order placed on Testnet, trade recorded in DB ✓
7. /positions → shows open position ✓
8. Dashboard → capital block shows correct values ✓
9. Dashboard → Chart.js renders (even empty) ✓
10. docker-compose up → all services start ✓
```

### Manual Smoke Test

```bash
# 1. Set up
cp .env.example .env  # Fill in API keys
docker-compose up -d

# 2. Verify Telegram
# Send: /init 100
# Expect: "Starting capital: 100.00 USDT"
# Send: /balance
# Expect: Balance showing 100.00 USDT

# 3. Verify Dashboard
curl http://localhost:5000/api/capital
# Expect: {"starting_capital": 100.0, "net_pnl": 0.0, "current_balance": 100.0}

# 4. Verify Logs
docker-compose logs bot | grep "Starting"
# Expect: "Starting Binance Trading Bot..."
```

---

## Key Configuration

### .env (secrets — never commit)

```bash
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true

TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_ADMIN_IDS=123456789

DATABASE_URL=sqlite:///data/trading_bot.db

FLASK_HOST=0.0.0.0
FLASK_PORT=5000

LOG_LEVEL=INFO
```

### config.yaml (parameters — committed)

```yaml
starting_capital:
  testnet: 100
  mainnet: 1000

capital:
  per_trade_usdt: 15
  min_trade_usdt: 10
  max_open_positions: 7
  reserved_usdt: 20

fees:
  fee_rate: 0.001
  breakeven_pct: 0.2

trading_pairs:
  core: ["BTC", "ETH", "SOL"]

logging:
  level: INFO
  rotation: "10 MB"
  retention: "7 days"
```

---

## Provenance Index

| Claim | Source |
|-------|--------|
| python-binance 1.0.37, supports Testnet via `testnet=True` | [VERIFIED: pypi.org/project/python-binance] |
| python-binance has `AsyncClient`, `ThreadedWebsocketManager` | [VERIFIED: pypi.org/project/python-binance description] |
| python-telegram-bot 22.8, requires Python ≥3.10 | [VERIFIED: pypi.org/project/python-telegram-bot] |
| python-telegram-bot `[job-queue]` extra installs APScheduler | [VERIFIED: pypi.org/project/python-telegram-bot deps] |
| SQLAlchemy 2.0.51, `DeclarativeBase` + `mapped_column` | [VERIFIED: pypi.org/project/SQLAlchemy] |
| Flask 3.1.3, Python ≥3.9 | [VERIFIED: pypi.org/project/Flask] |
| Binance MIN_NOTIONAL filter exists | [CITED: binance-trading-bot spec §3.5] |
| Fee rate 0.1% per side | [CITED: binance-bot spec §11.1] |
| Symbol format: API uses `BTCUSDT`, DB uses `BTC` | [CITED: binance-bot spec §9.2] |
| python-telegram-bot is NOT thread-safe | [CITED: python-telegram-bot docs "Concurrency"] |
| APScheduler BackgroundScheduler vs AsyncIOScheduler | [ASSUMED: standard APScheduler patterns] |

---

*Research completed: 2026-06-16*
