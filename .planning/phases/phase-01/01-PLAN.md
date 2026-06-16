---
wave: 1
depends_on: []
files_modified:
  - requirements.txt
  - .env.example
  - config.yaml
  - src/__init__.py
  - src/main.py
  - src/core/__init__.py
  - src/core/constants.py
  - src/core/binance_client.py
  - src/core/capital.py
  - src/core/ws_manager.py
  - src/database/__init__.py
  - src/database/models.py
  - src/database/session.py
  - src/database/migrations.py
  - src/strategies/__init__.py
  - src/indicators/__init__.py
  - src/learning/__init__.py
requirements_addressed:
  - INFRA-01
  - INFRA-03
  - INFRA-04
  - INFRA-05
  - BNCA-01
  - BNCA-02
  - BNCA-03
  - BNCA-04
  - DB-01
  - DB-02
  - DB-03
  - DB-04
  - PAIR-01
autonomous: true
---

# Plan 1: Project Scaffold + DB + Binance Client

<objective>
Create the full project scaffold with all directories, config files, database models (SQLAlchemy 2.0 style), database session factory, Binance REST client wrapper with testnet support, capital tracking module, and constants. By end of this plan: `python src/main.py` initializes without error, connects to Binance Testnet, and creates all SQLite tables.
</objective>

<tasks>

## Task 1.1: Create project structure and config files

<read_first>
  - binance_bot_spec_v2.md §14 (Configuration)
  - .planning/REQUIREMENTS.md (INFRA-01, INFRA-03, INFRA-04, INFRA-05)
  - .planning/phases/phase-01/01-RESEARCH.md (Configuration section)
</read_first>

<action>
1. Create directory structure:
   ```
   src/
   ├── __init__.py
   ├── main.py
   ├── core/
   │   ├── __init__.py
   │   ├── constants.py
   │   ├── binance_client.py
   │   ├── capital.py
   │   └── ws_manager.py
   ├── database/
   │   ├── __init__.py
   │   ├── models.py
   │   ├── session.py
   │   └── migrations.py
   ├── telegram_bot/
   │   ├── __init__.py
   │   ├── app.py
   │   └── handlers.py
   ├── dashboard/
   │   ├── __init__.py
   │   ├── app.py
   │   ├── routes.py
   │   └── templates/
   │       └── index.html
   ├── strategies/__init__.py
   ├── indicators/__init__.py
   └── learning/__init__.py
   ```

2. Create `requirements.txt` with EXACT versions from research (NO ML/strategy deps):
   ```
   python-binance==1.0.37
   python-telegram-bot==22.8
   flask==3.1.3
   flask-sqlalchemy==3.1.1
   sqlalchemy==2.0.51
   apscheduler==3.10.4
   loguru==0.7.2
   python-dotenv==1.0.0
   pyyaml==6.0.1
   pandas==2.1.4
   numpy==1.26.2
   ```

3. Create `.env.example`:
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

4. Create `config.yaml`:
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

5. Create `src/core/constants.py`:
   ```python
   FEE_RATE = 0.001
   BREAKEVEN_PCT = 0.002
   MIN_TRADE_USDT = 10
   DEFAULT_PER_TRADE_USDT = 15
   MAX_OPEN_POSITIONS = 7
   RESERVED_USDT = 20
   CORE_PAIRS = ["BTC", "ETH", "SOL"]
   ```

6. Create empty `__init__.py` files for all packages.
</action>

<acceptance_criteria>
- [ ] All directories and files exist per the structure above
- [ ] `requirements.txt` contains exactly 11 packages with pinned versions, NO ML deps
- [ ] `.env.example` has all required environment variables
- [ ] `config.yaml` loads correctly with `yaml.safe_load(open("config.yaml"))`
- [ ] `python -c "from core.constants import FEE_RATE; print(FEE_RATE)"` returns `0.001` when run from `src/`
- [ ] No import errors when running `python -c "import src"` from project root
</acceptance_criteria>

## Task 1.2: Database models (SQLAlchemy 2.0 style)

<read_first>
  - binance_bot_spec_v2.md §9 (Database tables)
  - .planning/phases/phase-01/01-RESEARCH.md (SQLAlchemy Models section)
  - .planning/REQUIREMENTS.md (DB-01, DB-02, DB-03, DB-04)
</read_first>

<action>
1. Create `src/database/models.py` with SQLAlchemy 2.0 `DeclarativeBase` + `mapped_column` style. Define ALL four tables:

   **Base class:**
   ```python
   from sqlalchemy.orm import DeclarativeBase

   class Base(DeclarativeBase):
       pass
   ```

   **BotSession model (DB-02):**
   ```python
   from sqlalchemy import String, Float, Integer, DateTime, func
   from sqlalchemy.orm import Mapped, mapped_column

   class BotSession(Base):
       __tablename__ = "bot_session"
       id: Mapped[int] = mapped_column(primary_key=True)
       starting_capital: Mapped[float] = mapped_column(Float, nullable=False)
       started_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
       mode: Mapped[str] = mapped_column(String(10), nullable=False)  # testnet/mainnet
       total_trades: Mapped[int] = mapped_column(Integer, default=0)
       total_net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
       max_balance: Mapped[float] = mapped_column(Float, default=0.0)
       current_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
       status: Mapped[str] = mapped_column(String(10), default="active")
       created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
       updated_at: Mapped[DateTime] = mapped_column(DateTime, onupdate=func.now())
   ```

   **Trade model (DB-01):**
   - `order_id` (String(64), unique, not null)
   - `symbol` (String(10), not null) — stores base asset only: "BTC", "ETH"
   - `side` (String(4), not null) — "BUY" / "SELL"
   - `type` (String(10), not null) — "MARKET" / "LIMIT"
   - `strategy` (String(20), nullable)
   - `quantity` (Float, not null)
   - `price` (Float, not null)
   - `total_usdt` (Float, not null)
   - `fee_rate` (Float, default=0.001)
   - `fee_buy` (Float, default=0.0)
   - `fee_sell` (Float, default=0.0)
   - `fee_total` (Float, default=0.0)
   - `gross_pnl` (Float, default=0.0)
   - `net_pnl` (Float, default=0.0)
   - `net_pnl_pct` (Float, default=0.0)
   - `status` (String(10), not null) — "OPEN" / "CLOSED" / "CANCELLED"
   - `opened_at` (DateTime, not null)
   - `closed_at` (DateTime, nullable)
   - `created_at` (DateTime, server_default=func.now())

   **ModelHistory model (DB-03):**
   - `strategy` (String(20), not null)
   - `model_type` (String(20), not null) — "params" / "weights" / "rl_agent"
   - `params_before` (Text, nullable) — JSON
   - `params_after` (Text, nullable) — JSON
   - `sharpe_before` (Float, nullable)
   - `sharpe_after` (Float, nullable)
   - `win_rate_before` (Float, nullable)
   - `win_rate_after` (Float, nullable)
   - `trades_count` (Integer, nullable)
   - `applied` (Boolean, default=True)
   - `created_at` (DateTime, server_default=func.now())

   **Alert model (DB-04):**
   - `type` (String(10), not null) — "trade" / "anomaly" / "learn" / "error"
   - `symbol` (String(10), nullable)
   - `message` (Text, not null)
   - `sent` (Boolean, default=False)
   - `created_at` (DateTime, server_default=func.now())
</action>

<acceptance_criteria>
- [ ] `python -c "from src.database.models import Base, BotSession, Trade, ModelHistory, Alert"` succeeds
- [ ] All 4 tables have correct columns matching spec §9 exactly
- [ ] `Trade.symbol` stores "BTC" not "BTCUSDT"
- [ ] `BotSession.mode` supports "testnet"/"mainnet" values
- [ ] All Float columns have sensible defaults (0.0, not None)
</acceptance_criteria>

## Task 1.3: Database session factory and migrations

<read_first>
  - .planning/phases/phase-01/01-RESEARCH.md (Database Session Pattern section)
  - .planning/REQUIREMENTS.md (INFRA-04)
</read_first>

<action>
1. Create `src/database/session.py`:
   ```python
   import os
   from sqlalchemy import create_engine
   from sqlalchemy.orm import sessionmaker

   DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/trading_bot.db")
   engine = create_engine(DATABASE_URL, echo=False)
   SessionLocal = sessionmaker(bind=engine)

   def get_db():
       db = SessionLocal()
       try:
           yield db
       finally:
           db.close()
   ```

2. Create `src/database/migrations.py`:
   ```python
   from src.database.models import Base
   from src.database.session import engine

   def run_migrations():
       Base.metadata.create_all(bind=engine)
   ```

3. Wire migrations into `src/main.py` — call `run_migrations()` on startup before any DB operations.
</action>

<acceptance_criteria>
- [ ] `python -c "from src.database.session import engine, SessionLocal, get_db"` succeeds
- [ ] `python -c "from src.database.migrations import run_migrations; run_migrations()"` creates tables
- [ ] After running migrations, `trades`, `bot_session`, `model_history`, `alerts` tables exist in SQLite
- [ ] `DATABASE_URL` defaults to `sqlite:///data/trading_bot.db` when env var not set
</acceptance_criteria>

## Task 1.4: Binance client wrapper

<read_first>
  - .planning/phases/phase-01/01-RESEARCH.md (Binance Client Wrapper, Common Pitfalls sections)
  - binance_bot_spec_v2.md §11 (Fee accounting)
  - .planning/REQUIREMENTS.md (BNCA-01, BNCA-03, BNCA-04)
</read_first>

<action>
1. Create `src/core/binance_client.py` with `BinanceClient` class:

   ```python
   from binance.client import Client
   from binance.exceptions import BinanceAPIException
   from loguru import logger

   class BinanceClient:
       def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
           self.client = Client(api_key, api_secret, testnet=testnet)
           self.testnet = testnet
           self._symbol_info_cache = {}

       def get_balance(self, asset: str = "USDT") -> float:
           account = self.client.get_account()
           for balance in account["balances"]:
               if balance["asset"] == asset:
                   return float(balance["free"])
           return 0.0

       def get_price(self, symbol: str) -> float:
           ticker = self.client.get_symbol_ticker(symbol=f"{symbol}USDT")
           return float(ticker["price"])

       def get_symbol_info(self, symbol: str) -> dict:
           if symbol not in self._symbol_info_cache:
               self._symbol_info_cache[symbol] = self.client.get_symbol_info(f"{symbol}USDT")
           return self._symbol_info_cache[symbol]

       def get_min_notional(self, symbol: str) -> float:
           info = self.get_symbol_info(symbol)
           for f in info["filters"]:
               if f["filterType"] == "NOTIONAL":
                   return float(f["minNotional"])
           return 10.0

        def quantity_precision(self, symbol: str) -> int:
            info = self.get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    step = float(f["stepSize"])
                    return len(str(step).rstrip("0").split(".")[-1]) if "." in str(step) else 0
            return 8

        def price_precision(self, symbol: str) -> int:
            info = self.get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"] == "PRICE_FILTER":
                    tick = float(f["tickSize"])
                    return len(str(tick).rstrip("0").split(".")[-1]) if "." in str(tick) else 0
            return 8

        def get_step_size(self, symbol: str) -> float:
            info = self.get_symbol_info(symbol)
            for f in info["filters"]:
                if f["filterType"] == "LOT_SIZE":
                    return float(f["stepSize"])
            return 0.00001

       def place_market_buy(self, symbol: str, quote_qty: float) -> dict:
           precision = self.quantity_precision(symbol)
           price = self.get_price(symbol)
           qty = round(quote_qty / price, precision)
           return self.client.create_order(
               symbol=f"{symbol}USDT",
               side=Client.SIDE_BUY,
               type=Client.ORDER_TYPE_MARKET,
               quantity=qty,
           )

       def place_market_sell(self, symbol: str, quantity: float) -> dict:
           precision = self.quantity_precision(symbol)
           qty = round(quantity, precision)
           return self.client.create_order(
               symbol=f"{symbol}USDT",
               side=Client.SIDE_SELL,
               type=Client.ORDER_TYPE_MARKET,
               quantity=qty,
           )

       def get_open_orders(self, symbol: str = None) -> list:
           return self.client.get_open_orders(symbol=f"{symbol}USDT" if symbol else None)

       def cancel_order(self, symbol: str, order_id: int) -> dict:
           return self.client.cancel_order(symbol=f"{symbol}USDT", orderId=order_id)
   ```

2. Wrap all API calls in try/except BinanceAPIException with logging:
   ```python
   try:
       # API call
   except BinanceAPIException as e:
       logger.error(f"Binance API error: {e.status_code} - {e.message}")
       raise
   ```

3. Symbol conversion: always convert between `symbol` (DB: "BTC") and `symbol+"USDT"` (API: "BTCUSDT").
</action>

<acceptance_criteria>
- [ ] `BinanceClient("key", "secret", testnet=True)` creates a client without error
- [ ] `get_balance()` returns a float (even 0.0)
- [ ] `get_price("BTC")` returns a float > 0
- [ ] `get_min_notional("BTC")` returns a float > 0
- [ ] `quantity_precision("BTC")` returns an int (decimal places)
- [ ] `price_precision("BTC")` returns an int (decimal places)
- [ ] All API calls are wrapped in try/except BinanceAPIException
- [ ] Symbol conversion works: "BTC" → "BTCUSDT" for API, "BTCUSDT" → "BTC" for DB
</acceptance_criteria>

## Task 1.5: Capital tracking module

<read_first>
  - binance_bot_spec_v2.md §10 (Capital management), §11 (Fee accounting)
  - .planning/REQUIREMENTS.md (CAP-01, CAP-02)
  - .planning/phases/phase-01/01-RESEARCH.md (Capital tracking code pattern)
</read_first>

<action>
1. Create `src/core/capital.py`:
   ```python
   from datetime import datetime
   from sqlalchemy import func
   from src.database.session import SessionLocal
   from src.database.models import BotSession, Trade
   from src.core.constants import FEE_RATE

   def init_capital(amount: float, mode: str = "testnet") -> BotSession:
       db = SessionLocal()
       try:
           session = BotSession(
               starting_capital=amount,
               started_at=datetime.utcnow(),
               mode=mode,
               total_trades=0,
               total_net_pnl=0.0,
               max_balance=amount,
               current_drawdown=0.0,
               status="active",
           )
           db.add(session)
           db.commit()
           return session
       finally:
           db.close()

    def get_capital_info() -> dict:
        db = SessionLocal()
        try:
            session = db.query(BotSession).order_by(-BotSession.id).first()
            if not session:
                return None

            net_pnl = db.query(func.coalesce(func.sum(Trade.net_pnl), 0.0)).filter(
                Trade.status == "CLOSED"
            ).scalar()

            unrealized_pnl = db.query(func.coalesce(func.sum(Trade.gross_pnl), 0.0)).filter(
                Trade.status == "OPEN"
            ).scalar()

            current_balance = session.starting_capital + net_pnl

            return {
                "starting_capital": session.starting_capital,
                "net_pnl": net_pnl,
                "unrealized_pnl": unrealized_pnl,
                "current_balance": current_balance,
                "total_with_open": current_balance + unrealized_pnl,
                "max_balance": session.max_balance,
                "drawdown_pct": session.current_drawdown,
                "roi_pct": (net_pnl / session.starting_capital * 100) if session.starting_capital > 0 else 0,
            }
        finally:
            db.close()

    def update_drawdown_stats() -> None:
        db = SessionLocal()
        try:
            session = db.query(BotSession).order_by(-BotSession.id).first()
            if not session:
                return

            net_pnl = db.query(func.coalesce(func.sum(Trade.net_pnl), 0.0)).filter(
                Trade.status == "CLOSED"
            ).scalar()

            current_balance = session.starting_capital + net_pnl

            if current_balance > session.max_balance:
                session.max_balance = current_balance
            if session.max_balance > 0:
                session.current_drawdown = (session.max_balance - current_balance) / session.max_balance * 100
            db.commit()
        finally:
            db.close()

   def calc_pnl(buy_price: float, sell_price: float, qty: float) -> dict:
       buy_total = buy_price * qty
       sell_total = sell_price * qty
       fee_buy = buy_total * FEE_RATE
       fee_sell = sell_total * FEE_RATE
       gross_pnl = sell_total - buy_total
       net_pnl = gross_pnl - fee_buy - fee_sell
       return {
           "gross_pnl": round(gross_pnl, 4),
           "fee_buy": round(fee_buy, 4),
           "fee_sell": round(fee_sell, 4),
           "fee_total": round(fee_buy + fee_sell, 4),
           "net_pnl": round(net_pnl, 4),
           "net_pnl_pct": round(net_pnl / buy_total * 100, 3) if buy_total > 0 else 0,
       }
   ```

2. `init_capital` creates a BotSession row with `starting_capital`, `started_at=now()`, `mode`.
3. `get_capital_info` is a pure read function — returns dict with all three tracking values (starting_capital, net_pnl, current_balance) plus max_balance, drawdown, ROI. Does NOT mutate state.
4. `update_drawdown_stats` updates max_balance and current_drawdown in DB. Call after each trade close.
5. `calc_pnl` computes gross_pnl, fees (0.1% each side), net_pnl, net_pnl_pct — all per spec §11.2.
</action>

<acceptance_criteria>
- [ ] `init_capital(100.0, "testnet")` inserts a BotSession row with starting_capital=100.0
- [ ] `get_capital_info()` returns dict with keys: starting_capital, net_pnl, current_balance, max_balance, drawdown_pct, roi_pct
- [ ] `calc_pnl(100, 105, 0.15)` returns correct net_pnl = 105*0.15 - 100*0.15 - fees = 0.75 - 0.015 - 0.01575 ≈ 0.7193
- [ ] `calc_pnl` uses FEE_RATE=0.001 for both buy and sell fees
- [ ] When no BotSession exists, `get_capital_info()` returns None
</acceptance_criteria>

## Task 1.6: WebSocket manager for live price data

<read_first>
  - .planning/phases/phase-01/01-RESEARCH.md (Binance Client Wrapper, Common Pitfalls sections)
  - .planning/REQUIREMENTS.md (BNCA-02)
  - binance_bot_spec_v2.md §11 (Fee accounting — live prices)
</read_first>

<action>
1. Create `src/core/ws_manager.py` with `WSManager` class:

   ```python
   from binance import ThreadedWebsocketManager
   from loguru import logger
   from typing import Callable, Optional

   class WSManager:
       def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
           self.twm = ThreadedWebsocketManager(api_key=api_key, api_secret=api_secret, testnet=testnet)
           self._streams: dict[str, str] = {}
           self._callbacks: dict[str, Callable] = {}

       def start(self):
           self.twm.start()
           logger.info("WebSocket manager started")

       def stop(self):
           for symbol, stream_name in self._streams.items():
               self.twm.stop_socket(stream_name)
           self.twm.stop()
           self._streams.clear()
           self._callbacks.clear()
           logger.info("WebSocket manager stopped")

       def subscribe_kline(self, symbol: str, interval: str, callback: Callable):
           key = f"{symbol}_{interval}"
           if key in self._streams:
               logger.warning(f"Already subscribed to {key}")
               return
           stream_name = self.twm.start_kline_socket(
               callback=callback,
               symbol=f"{symbol}USDT",
               interval=interval,
           )
           self._streams[key] = stream_name
           self._callbacks[key] = callback
           logger.info(f"Subscribed to {symbol} {interval} klines")

       def subscribe_ticker(self, symbol: str, callback: Callable):
           key = f"{symbol}_ticker"
           if key in self._streams:
               logger.warning(f"Already subscribed to {key}")
               return
           stream_name = self.twm.start_symbol_ticker_socket(
               callback=callback,
               symbol=f"{symbol}USDT",
           )
           self._streams[key] = stream_name
           self._callbacks[key] = callback
           logger.info(f"Subscribed to {symbol} ticker")

       def unsubscribe(self, symbol: str, interval: Optional[str] = None):
           if interval:
               key = f"{symbol}_{interval}"
           else:
               # Remove all streams for this symbol
               keys = [k for k in self._streams if k.startswith(f"{symbol}_")]
               for k in keys:
                   self.twm.stop_socket(self._streams.pop(k))
                   self._callbacks.pop(k, None)
               return
           if key in self._streams:
               self.twm.stop_socket(self._streams.pop(key))
               self._callbacks.pop(key, None)
   ```

2. Key design points:
   - `ThreadedWebsocketManager` from `python-binance` — already a dependency
   - All symbols use `symbol+"USDT"` for API, but internal keys use base asset only ("BTC")
   - `subscribe_kline` for live candlestick data (used by strategies)
   - `subscribe_ticker` for live price ticks (used by dashboard, positions)
   - `stop()` cleanly shuts down all streams
   - Each callback receives raw Binance WS message dict
</action>

<acceptance_criteria>
- [ ] `WSManager("key", "secret", testnet=True)` creates instance without error
- [ ] `start()` / `stop()` lifecycle works without hanging threads
- [ ] `subscribe_kline("BTC", "1m", callback)` subscribes to BTCUSDT kline stream
- [ ] `subscribe_ticker("ETH", callback)` subscribes to ETHUSDT ticker stream
- [ ] `unsubscribe("BTC", "1m")` removes only that stream
- [ ] `stop()` removes all streams and stops the manager
- [ ] Internal keys use base asset only ("BTC"), not "BTCUSDT"
</acceptance_criteria>

## Task 1.7: Main entry point skeleton

<read_first>
  - .planning/phases/phase-01/01-RESEARCH.md (Main Entry Point section)
  - .planning/REQUIREMENTS.md (INFRA-05)
  - src/core/ws_manager.py (WSManager)
</read_first>

<action>
1. Create `src/main.py`:
   ```python
   import os
   import sys
   import threading
   from loguru import logger
   from dotenv import load_dotenv

   load_dotenv()

   # Configure loguru
   logger.remove()
   logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))
   logger.add("logs/bot.log", rotation="10 MB", retention="7 days", level="DEBUG")

   def main():
       logger.info("Starting Binance Trading Bot...")

       # Run migrations
       from src.database.migrations import run_migrations
       run_migrations()
       logger.info("Database migrations complete")

       # TODO: Start Flask dashboard (Plan 3)
       # TODO: Start Telegram bot (Plan 2)
       # TODO: Start WSManager for live data (see Task 1.6)
       # TODO: Start APScheduler (Plan 2)

       logger.info("Bot initialized. Waiting for Telegram connection...")

   if __name__ == "__main__":
       main()
   ```

2. Create `logs/` directory (gitkeep it).
3. Verify: `cd src && python main.py` starts without import errors (may fail on missing .env keys, but no ImportErrors).
</action>

<acceptance_criteria>
- [ ] `python src/main.py` runs without ImportError
- [ ] Log files are created in `logs/` directory
- [ ] "Starting Binance Trading Bot..." appears in logs
- [ ] "Database migrations complete" appears in logs
- [ ] No ML/strategy dependencies imported (no pandas-ta, optuna, stable-baselines3)
</acceptance_criteria>

</tasks>

<must_haves>
- Project structure matches INFRA-01 exactly
- All 4 DB tables created with correct schema from spec §9
- BinanceClient supports testnet=True, get_balance, get_price, get_min_notional, place_market_buy, place_market_sell
- WSManager supports start/stop lifecycle, subscribe_kline, subscribe_ticker
- Capital tracking: init_capital, get_capital_info, calc_pnl — all per spec §9.2, §11.2
- Symbol conversion: DB uses "BTC", API uses "BTCUSDT" — never mixed up
- Loguru configured with file rotation + stdout
- Config loaded from .env + config.yaml
- NO ML dependencies installed
</must_haves>

## Artifacts this phase produces

- `requirements.txt` — pinned dependencies (no ML deps)
- `.env.example` — environment variable template
- `config.yaml` — default configuration
- `src/core/constants.py` — FEE_RATE, MIN_TRADE_USDT, CORE_PAIRS
- `src/database/models.py` — BotSession, Trade, ModelHistory, Alert models
- `src/database/session.py` — engine, SessionLocal, get_db
- `src/database/migrations.py` — run_migrations()
- `src/core/binance_client.py` — BinanceClient wrapper
- `src/core/capital.py` — init_capital, get_capital_info, calc_pnl
- `src/core/ws_manager.py` — WSManager for live kline/ticker streams
- `src/main.py` — entry point skeleton
- All `__init__.py` files
