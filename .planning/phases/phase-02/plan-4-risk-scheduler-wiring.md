---
wave: 4
depends_on:
  - plan-3-mtf-autoselector.md
files_modified:
  - src/core/risk_manager.py
  - src/strategies/manager.py
  - src/main.py
  - src/strategies/__init__.py
requirements_addressed:
  - RISK-01
  - RISK-02
  - RISK-03
  - RISK-04
autonomous: true
---

# Plan 4 — Risk Manager + Strategy Manager + APScheduler + main.py Wiring

<objective>
Create the Risk Manager that enforces all 4 risk rules (max positions, daily loss, reserve buffer, cooldown). Build the Strategy Manager that orchestrates strategy ticks via APScheduler. Wire everything into main.py so the bot starts trading automatically with the active strategy.
</objective>

---

## Task 4.1 — Create Risk Manager

<read_first>
- src/core/constants.py (MAX_OPEN_POSITIONS, RESERVED_USDT, FEE_RATE)
- src/core/capital.py (get_capital_info — returns dict with starting_capital, current_balance, drawdown_pct)
- src/database/models.py (Trade model — status field, net_pnl field)
- src/database/session.py (SessionLocal)
- binance_bot_spec_v2.md §6.4 (Anomaly Guard: drawdown > 8% stop)
- 02-RESEARCH.md "Risk Manager Implementation" section
- config.yaml (risk section)
</read_first>

<action>
1. Write `src/core/risk_manager.py`:

```python
from datetime import datetime, timedelta
from loguru import logger
from src.core.constants import MAX_OPEN_POSITIONS, RESERVED_USDT
from src.core.capital import get_capital_info
from src.database.session import SessionLocal
from src.database.models import Trade


class RiskManager:
    """Enforces risk limits before every trade."""

    DAILY_LOSS_LIMIT_PCT = 5.0
    COOLDOWN_MINUTES = 15
    MAX_DRAWDOWN_PCT = 8.0

    def __init__(self, config: dict = None):
        if config:
            risk_cfg = config.get("risk", {})
            self.DAILY_LOSS_LIMIT_PCT = risk_cfg.get("daily_loss_limit_pct", 5.0)
            self.COOLDOWN_MINUTES = risk_cfg.get("cooldown_minutes", 15)
        self._cooldown_until: dict[str, datetime] = {}

    def can_trade(self, symbol: str) -> tuple[bool, str]:
        """Check all risk conditions. Returns (allowed, reason)."""

        # RISK-01: Max positions
        open_count = self._count_open_positions()
        if open_count >= MAX_OPEN_POSITIONS:
            return False, f"Max positions reached ({open_count}/{MAX_OPEN_POSITIONS})"

        # RISK-02: Daily loss limit
        daily_pnl = self._get_daily_pnl()
        capital_info = get_capital_info()
        if capital_info:
            daily_limit = capital_info["starting_capital"] * self.DAILY_LOSS_LIMIT_PCT / 100
            if daily_pnl < -daily_limit:
                return False, f"Daily loss limit: {daily_pnl:.2f} USDT (limit: -{daily_limit:.2f})"

        # RISK-03: Reserve buffer
        if capital_info:
            available = capital_info["current_balance"] - RESERVED_USDT
            if available < 0:
                return False, f"Reserve buffer: balance {capital_info['current_balance']:.2f} < {RESERVED_USDT} USDT"

        # RISK-04: Cooldown after stop-loss
        now = datetime.utcnow()
        if symbol in self._cooldown_until:
            if now < self._cooldown_until[symbol]:
                remaining = int((self._cooldown_until[symbol] - now).total_seconds() // 60)
                return False, f"Cooldown: {remaining} min remaining for {symbol}"

        return True, "OK"

    def trigger_cooldown(self, symbol: str):
        """Start cooldown after stop-loss execution."""
        self._cooldown_until[symbol] = datetime.utcnow() + timedelta(minutes=self.COOLDOWN_MINUTES)
        logger.info(f"RiskManager: cooldown {self.COOLDOWN_MINUTES}min started for {symbol}")

    def check_drawdown(self) -> bool:
        """Returns True if drawdown > 8% — should stop all trading."""
        capital_info = get_capital_info()
        if not capital_info:
            return False
        if capital_info["drawdown_pct"] > self.MAX_DRAWDOWN_PCT:
            logger.warning(f"RiskManager: drawdown {capital_info['drawdown_pct']:.2f}% > {self.MAX_DRAWDOWN_PCT}% — STOP TRADING")
            return True
        return False

    def get_status(self) -> dict:
        """Return current risk status for monitoring."""
        capital_info = get_capital_info()
        open_count = self._count_open_positions()
        daily_pnl = self._get_daily_pnl()
        return {
            "open_positions": open_count,
            "max_positions": MAX_OPEN_POSITIONS,
            "daily_pnl": round(daily_pnl, 4),
            "daily_loss_limit": round(
                capital_info["starting_capital"] * self.DAILY_LOSS_LIMIT_PCT / 100, 4
            ) if capital_info else 0,
            "drawdown_pct": capital_info["drawdown_pct"] if capital_info else 0,
            "cooldowns": {
                sym: exp.isoformat()
                for sym, exp in self._cooldown_until.items()
                if exp > datetime.utcnow()
            },
        }

    def _count_open_positions(self) -> int:
        db = SessionLocal()
        try:
            return db.query(Trade).filter(Trade.status == "OPEN").count()
        finally:
            db.close()

    def _get_daily_pnl(self) -> float:
        """Sum of net_pnl for trades closed today (UTC)."""
        db = SessionLocal()
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            result = db.query(Trade.net_pnl).filter(
                Trade.status == "CLOSED",
                Trade.closed_at >= today_start,
            ).all()
            return sum(r[0] for r in result) if result else 0.0
        finally:
            db.close()
```
</action>

<acceptance_criteria>
- `from src.core.risk_manager import RiskManager` works
- `can_trade(symbol)` returns (True, "OK") when all conditions met
- Returns (False, ...) when max positions reached (RISK-01)
- Returns (False, ...) when daily loss exceeds 5% of starting capital (RISK-02)
- Returns (False, ...) when balance < reserved_usdt (RISK-03)
- Returns (False, ...) during cooldown period (RISK-04)
- `trigger_cooldown(symbol)` starts 15-minute cooldown
- `check_drawdown()` returns True when drawdown > 8%
- `get_status()` returns dict with all risk metrics
- Daily PnL resets at midnight UTC
- Cooldown is per-symbol (BTC cooldown doesn't block ETH)
- SQLite sessions are created per-call (thread-safe)
</acceptance_criteria>

---

## Task 4.2 — Create Strategy Manager

<read_first>
- src/strategies/base.py (BaseStrategy, Signal, TradeAction)
- src/strategies/__init__.py (ALL_STRATEGIES)
- src/strategies/auto_selector.py (AutoSelector)
- src/core/binance_client.py (get_price, place_market_buy, place_market_sell)
- src/core/risk_manager.py (RiskManager)
- src/core/capital.py (calc_pnl)
- src/core/constants.py (FEE_RATE, CORE_PAIRS)
- src/database/session.py (SessionLocal)
- src/database/models.py (Trade)
- src/indicators/__init__.py (calc_indicators)
- 02-RESEARCH.md "Complete Strategy Tick Flow" section
</read_first>

<action>
1. Write `src/strategies/manager.py`:

```python
import time
from datetime import datetime
from loguru import logger
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.strategies.auto_selector import AutoSelector
from src.core.risk_manager import RiskManager
from src.core.capital import calc_pnl
from src.core.constants import FEE_RATE, CORE_PAIRS
from src.database.session import SessionLocal
from src.database.models import Trade


class StrategyManager:
    """Orchestrates all strategies, handles tick execution, manages state."""

    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        self.config = config
        self.strategies: dict[str, BaseStrategy] = {}
        self.active_name: str | None = None
        self.auto_mode = True
        self.risk_manager = RiskManager(config)
        self.auto_selector = AutoSelector(binance_client, config)
        self._pairs = config.get("trading_pairs", {}).get("core", CORE_PAIRS)

    def register(self, name: str, strategy: BaseStrategy):
        self.strategies[name] = strategy
        logger.info(f"Strategy registered: {name}")

    def set_active(self, name: str):
        if name == "auto":
            self.auto_mode = True
            logger.info("Strategy mode: AUTO")
        elif name in self.strategies:
            self.active_name = name
            self.auto_mode = False
            logger.info(f"Strategy set to: {name}")
        else:
            logger.warning(f"Unknown strategy: {name}")

    def tick_all(self):
        """Called by APScheduler every N minutes."""
        for symbol in self._pairs:
            try:
                self.tick(symbol)
            except Exception as e:
                logger.error(f"Tick failed for {symbol}: {e}")

    def tick(self, symbol: str):
        """Execute one tick for a symbol."""
        # 1. Drawdown circuit breaker
        if self.risk_manager.check_drawdown():
            logger.debug(f"Tick skipped {symbol}: drawdown > 8%")
            return

        # 2. Risk check
        can_trade, reason = self.risk_manager.can_trade(symbol)
        if not can_trade:
            logger.debug(f"Risk blocked {symbol}: {reason}")
            return

        # 3. Auto-select strategy if in auto mode
        if self.auto_mode:
            strategy_name = self.auto_selector.select(symbol)
            strategy = self.strategies.get(strategy_name)
        else:
            strategy = self.strategies.get(self.active_name)

        if not strategy:
            logger.debug(f"No strategy for {symbol}")
            return

        # 4. Fetch data
        try:
            klines_raw = self.binance.client.get_klines(
                symbol=f"{symbol}USDT", interval="1h", limit=250,
            )
            klines = [{
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            } for k in klines_raw]
        except Exception as e:
            logger.error(f"Failed to fetch klines for {symbol}: {e}")
            return

        current_price = self.binance.get_price(symbol)

        # 5. Get open positions from DB
        open_positions = self._get_open_positions(symbol)

        # 6. Analyze
        action = strategy.analyze(symbol, klines, current_price, open_positions)

        # 7. Execute
        if action.signal == Signal.BUY:
            self._execute_buy(action, symbol, strategy.name)
        elif action.signal == Signal.SELL:
            self._execute_sell(action, symbol, strategy.name)

    def _execute_buy(self, action: TradeAction, symbol: str, strategy_name: str):
        """Execute a buy signal."""
        try:
            if action.quote_qty:
                order = self.binance.place_market_buy(symbol, action.quote_qty)
            elif action.price and action.quantity:
                order = self.binance.place_limit_buy(symbol, action.price, action.quantity)
            else:
                logger.warning(f"Buy action for {symbol} has no qty/quote_qty")
                return

            # Record trade in DB
            qty = float(order.get("executedQty", action.quantity or 0))
            price = float(order.get("price", action.price or 0))
            if price == 0:
                price = self.binance.get_price(symbol)
            total_usdt = qty * price

            db = SessionLocal()
            try:
                trade = Trade(
                    order_id=str(order["orderId"]),
                    symbol=symbol,
                    side="BUY",
                    type=order.get("type", "MARKET"),
                    strategy=strategy_name,
                    quantity=qty,
                    price=price,
                    total_usdt=total_usdt,
                    fee_rate=FEE_RATE,
                    fee_buy=total_usdt * FEE_RATE,
                    status="OPEN",
                    opened_at=datetime.utcnow(),
                )
                db.add(trade)
                db.commit()
                logger.info(f"BUY {symbol}: {qty:.6f} @ {price:.2f} ({strategy_name})")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Execute buy failed for {symbol}: {e}")

    def _execute_sell(self, action: TradeAction, symbol: str, strategy_name: str):
        """Execute a sell signal. Matches to open BUY trade, calculates net PnL."""
        try:
            if action.quantity:
                order = self.binance.place_market_sell(symbol, action.quantity)
            elif action.price and action.quantity:
                order = self.binance.place_limit_sell(symbol, action.price, action.quantity)
            else:
                logger.warning(f"Sell action for {symbol} has no quantity")
                return

            qty = float(order.get("executedQty", action.quantity or 0))
            sell_price = float(order.get("price", 0))
            if sell_price == 0:
                sell_price = self.binance.get_price(symbol)

            # Find matching OPEN trade for this symbol + strategy
            db = SessionLocal()
            try:
                open_trade = db.query(Trade).filter(
                    Trade.symbol == symbol,
                    Trade.side == "BUY",
                    Trade.status == "OPEN",
                    Trade.strategy == strategy_name,
                ).order_by(Trade.opened_at).first()

                if open_trade:
                    pnl = calc_pnl(open_trade.price, sell_price, open_trade.quantity)

                    # Update buy trade
                    open_trade.status = "CLOSED"
                    open_trade.closed_at = datetime.utcnow()
                    open_trade.fee_sell = qty * sell_price * FEE_RATE
                    open_trade.fee_total = open_trade.fee_buy + open_trade.fee_sell
                    open_trade.gross_pnl = pnl["gross_pnl"]
                    open_trade.net_pnl = pnl["net_pnl"]
                    open_trade.net_pnl_pct = pnl["net_pnl_pct"]

                    # Check if this was a stop-loss → trigger cooldown
                    if pnl["net_pnl_pct"] < 0:
                        self.risk_manager.trigger_cooldown(symbol)

                    db.commit()
                    logger.info(
                        f"SELL {symbol}: {qty:.6f} @ {sell_price:.2f} | "
                        f"net PnL: {pnl['net_pnl']:.4f} ({pnl['net_pnl_pct']:.2f}%)"
                    )
                else:
                    # Sell without matching buy — record as standalone sell
                    trade = Trade(
                        order_id=str(order["orderId"]),
                        symbol=symbol,
                        side="SELL",
                        type=order.get("type", "MARKET"),
                        strategy=strategy_name,
                        quantity=qty,
                        price=sell_price,
                        total_usdt=qty * sell_price,
                        fee_rate=FEE_RATE,
                        fee_sell=qty * sell_price * FEE_RATE,
                        status="CLOSED",
                        opened_at=datetime.utcnow(),
                        closed_at=datetime.utcnow(),
                    )
                    db.add(trade)
                    db.commit()
                    logger.info(f"SELL {symbol}: {qty:.6f} @ {sell_price:.2f} (no matching buy)")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Execute sell failed for {symbol}: {e}")

    def _get_open_positions(self, symbol: str) -> list:
        db = SessionLocal()
        try:
            trades = db.query(Trade).filter(
                Trade.symbol == symbol,
                Trade.side == "BUY",
                Trade.status == "OPEN",
            ).all()
            return [
                {"price": t.price, "quantity": t.quantity, "total_usdt": t.total_usdt}
                for t in trades
            ]
        finally:
            db.close()

    def get_status(self) -> dict:
        return {
            "active_strategy": "auto" if self.auto_mode else self.active_name,
            "strategies": list(self.strategies.keys()),
            "risk": self.risk_manager.get_status(),
        }
```
</action>

<acceptance_criteria>
- `from src.strategies.manager import StrategyManager` works
- StrategyManager accepts binance_client and config
- `register()` adds strategy to internal dict
- `set_active("auto")` enables auto mode, `set_active("grid")` sets fixed strategy
- `tick(symbol)` performs: risk check → fetch klines → analyze → execute
- `tick_all()` iterates all core pairs and calls tick for each
- Buy execution records Trade with status="OPEN" in DB
- Sell execution finds matching OPEN trade, calculates net PnL via calc_pnl, updates to CLOSED
- Stop-loss triggers cooldown on RiskManager
- Auto mode uses AutoSelector to pick strategy per symbol
- Drawdown > 8% blocks all trading
- SQLite sessions are created per-call (thread-safe)
</acceptance_criteria>

---

## Task 4.3 — Wire into main.py with APScheduler

<read_first>
- src/main.py (current entry point — starts dashboard and Telegram)
- src/strategies/manager.py (StrategyManager)
- src/strategies/__init__.py (ALL_STRATEGIES)
- src/core/binance_client.py (BinanceClient constructor)
- requirements.txt (apscheduler already present)
- .env (BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_TESTNET)
</read_first>

<action>
1. Rewrite `src/main.py`:

```python
import os
import sys
import threading
import yaml
from loguru import logger
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))
logger.add("logs/bot.log", rotation="10 MB", retention="7 days", level="DEBUG")


def load_config() -> dict:
    with open("config.yaml") as f:
        return yaml.safe_load(f)


def setup_strategies(binance_client, config: dict):
    """Initialize and register all strategies."""
    from src.strategies.manager import StrategyManager
    from src.strategies import ALL_STRATEGIES

    manager = StrategyManager(binance_client, config)

    for name, strategy_cls in ALL_STRATEGIES.items():
        strategy = strategy_cls(binance_client, config)
        manager.register(name, strategy)

    # Default to auto mode
    manager.set_active("auto")
    logger.info(f"Strategies registered: {list(ALL_STRATEGIES.keys())}")
    return manager


def setup_scheduler(strategy_manager) -> BackgroundScheduler:
    """Start APScheduler for strategy ticks every 5 minutes."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=strategy_manager.tick_all,
        trigger="interval",
        minutes=5,
        misfire_grace_time=60,
        id="strategy_tick",
    )
    scheduler.start()
    logger.info("APScheduler started: strategy tick every 5 minutes")
    return scheduler


def main():
    logger.info("Starting Binance Trading Bot...")

    # Database migrations
    from src.database.migrations import run_migrations
    run_migrations()
    logger.info("Database migrations complete")

    # Load config
    config = load_config()

    # Binance client
    from src.core.binance_client import BinanceClient
    binance_client = BinanceClient(
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
        testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
    )
    logger.info(f"Binance client initialized (testnet={binance_client.testnet})")

    # Strategy manager + all strategies
    strategy_manager = setup_strategies(binance_client, config)

    # APScheduler
    scheduler = setup_scheduler(strategy_manager)

    # Dashboard (in background thread)
    from src.dashboard.app import run_dashboard
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    logger.info("Dashboard started on port 5000")

    # Telegram bot (blocking — must be last)
    from src.telegram_bot.app import run_telegram_bot
    logger.info("Starting Telegram bot...")
    try:
        run_telegram_bot()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        scheduler.shutdown()
```
</action>

<acceptance_criteria>
- `python src/main.py` starts without ImportError
- Config is loaded from config.yaml
- BinanceClient is initialized with env vars
- All 4 strategies (grid, dca, rsi_ema, mtf) are registered in StrategyManager
- Auto mode is set by default
- APScheduler runs strategy_manager.tick_all every 5 minutes
- Dashboard starts in background thread
- Telegram bot starts last (blocking)
- Graceful shutdown on KeyboardInterrupt
</acceptance_criteria>

---

## Task 4.4 — Verify all 4 strategies import cleanly

<read_first>
- src/strategies/__init__.py (final version with all 4 strategies)
</read_first>

<action>
1. Run a verification script to ensure all imports work:

```bash
python -c "
from src.strategies import ALL_STRATEGIES, BaseStrategy, Signal, TradeAction
from src.strategies.auto_selector import AutoSelector
from src.core.risk_manager import RiskManager
from src.strategies.manager import StrategyManager
from src.indicators import calc_indicators, calc_rsi

print('ALL_STRATEGIES:', list(ALL_STRATEGIES.keys()))
assert len(ALL_STRATEGIES) == 4
assert 'grid' in ALL_STRATEGIES
assert 'dca' in ALL_STRATEGIES
assert 'rsi_ema' in ALL_STRATEGIES
assert 'mtf' in ALL_STRATEGIES
print('All imports OK')
"
```

2. Verify RiskManager rules work:

```bash
python -c "
from src.core.risk_manager import RiskManager
rm = RiskManager()
status = rm.get_status()
print('Risk status:', status)
assert 'open_positions' in status
assert 'daily_pnl' in status
assert 'drawdown_pct' in status
assert 'cooldowns' in status
print('RiskManager OK')
"
```

3. Verify indicator calculation:

```bash
python -c "
from src.indicators import calc_indicators
# Generate 250 dummy klines
klines = [{'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1000} for _ in range(250)]
result = calc_indicators(klines)
assert 'rsi' in result
assert 'ema200' in result
assert 'adx' in result
assert 'atr' in result
assert 'atr_pct' in result
assert all(isinstance(v, float) for v in result.values())
print('Indicators OK:', result)
"
```
</action>

<acceptance_criteria>
- All 4 strategies are importable from src.strategies
- ALL_STRATEGIES dict has exactly 4 entries: grid, dca, rsi_ema, mtf
- RiskManager can be instantiated and returns valid status dict
- calc_indicators returns valid floats for 250 dummy klines
- No ImportError or ModuleNotFoundError on any import
</acceptance_criteria>

---

## Artifacts this phase produces

| File | Purpose |
|------|---------|
| `src/core/risk_manager.py` | Risk enforcement: max positions, daily loss, reserve buffer, cooldown, drawdown breaker |
| `src/strategies/manager.py` | Strategy orchestration: tick loop, buy/sell execution, DB trade recording, PnL calculation |
| `src/main.py` | Rewired entry point: Binance → Strategies → Scheduler → Dashboard → Telegram |
| `src/strategies/__init__.py` | Final registry with all 4 strategies |
