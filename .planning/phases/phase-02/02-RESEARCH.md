# RESEARCH.md — Phase 2: Strategies

**Phase:** 2 — Стратегии (Strategies)
**Date:** 2026-06-16
**Goal:** 4 trading strategies with auto-selection and risk management — bot trades automatically

---

## Standard Stack

| Library | Version | Rationale |
|---------|---------|-----------|
| `pandas-ta` | **0.3.14b** | Spec-listed. Pure Python, no C dependencies. Returns pandas DataFrames. Supports RSI, EMA, ATR, ADX, and 130+ indicators. Install: `pip install pandas-ta`. [VERIFIED: pypi.org/project/pandas-ta] |
| `ta` | **0.11.0** | Alternative indicator library. Slightly faster for some indicators. Spec-listed as co-dependency. Use if pandas-ta has issues. [CITED: binance-bot spec §5] |
| `APScheduler` | **3.10.4** | Already installed (Phase 1). Use `BackgroundScheduler` for strategy tick jobs. Thread-safe for sync functions. [VERIFIED: Phase 1 requirements.txt] |
| `numpy` | **1.26.2** | Already installed. Required for ATR, EMA calculations. [VERIFIED: Phase 1 requirements.txt] |
| `pandas` | **2.1.4** | Already installed. Core data structure for kline OHLCV data. [VERIFIED: Phase 1 requirements.txt] |

**Do NOT add in Phase 2**: `scikit-learn`, `optuna`, `stable-baselines3` (Phase 3 — Learning Engine).

---

## Strategy Architecture

### Base Class Pattern

All strategies share a common interface. Use an abstract base class with concrete implementations:

```python
# src/strategies/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeAction:
    signal: Signal
    symbol: str
    quantity: float | None = None
    quote_qty: float | None = None
    price: float | None = None  # None = market order
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""


class BaseStrategy(ABC):
    """Base class for all trading strategies."""

    name: str = "base"

    @abstractmethod
    def analyze(self, symbol: str, klines: list, current_price: float,
                open_positions: list) -> TradeAction:
        """Analyze market data and return a trade action."""
        ...

    @abstractmethod
    def get_params(self) -> dict:
        """Return current strategy parameters (for optimization)."""
        ...

    @abstractmethod
    def set_params(self, params: dict) -> None:
        """Update strategy parameters (from optimization)."""
        ...
```

[ASSUMED: Standard plugin pattern for trading strategies]

### Strategy Manager

Orchestrates all strategies, handles tick execution, and manages state:

```python
# src/strategies/manager.py
class StrategyManager:
    def __init__(self, binance_client, risk_manager, config):
        self.binance = binance_client
        self.risk = risk_manager
        self.strategies = {}  # name -> BaseStrategy
        self.active_strategy = None
        self.config = config

    def register(self, strategy: BaseStrategy):
        self.strategies[strategy.name] = strategy

    def set_active(self, name: str):
        self.active_strategy = self.strategies.get(name)

    def tick(self, symbol: str):
        """Called by APScheduler every N minutes."""
        if not self.active_strategy:
            return

        klines = self._fetch_klines(symbol, "1h", 200)
        current_price = self.binance.get_price(symbol)
        open_positions = self._get_open_positions(symbol)

        action = self.active_strategy.analyze(
            symbol, klines, current_price, open_positions
        )

        if action.signal == Signal.BUY:
            self._execute_buy(action)
        elif action.signal == Signal.SELL:
            self._execute_sell(action)

    def _fetch_klines(self, symbol, interval, limit):
        """Fetch klines from Binance REST API."""
        raw = self.binance.client.get_klines(
            symbol=f"{symbol}USDT",
            interval=interval,
            limit=limit,
        )
        # Convert to list of dicts for pandas-ta
        return [{
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "open_time": k[0],
        } for k in raw]
```

[ASSUMED: Strategy manager pattern with tick-based execution]

### Plugin Registration

```python
# src/strategies/__init__.py
from src.strategies.base import BaseStrategy
from src.strategies.grid import GridStrategy
from src.strategies.dca import DCAStrategy
from src.strategies.rsi_ema import RSIEMAStrategy
from src.strategies.mtf import MTFMomentumStrategy

ALL_STRATEGIES = {
    "grid": GridStrategy,
    "dca": DCAStrategy,
    "rsi_ema": RSIEMAStrategy,
    "mtf": MTFMomentumStrategy,
}
```

[ASSUMED: Simple dict-based registry]

---

## Per-Strategy Implementation Details

### 1. Grid Trading (STRAT-01)

**Spec reference:** §6.1 — ФЛЭТ, ADX < 20

**Algorithm:**
1. Fetch current price and ATR(14) from 1h klines
2. Calculate grid range: `±(ATR * 2)` from current price
3. Calculate step: `max(0.005, ATR / current_price / grid_count)` — min 0.5%
4. Generate buy levels below price, sell levels above price
5. Place limit buy orders at each buy level
6. When a buy fills → place sell at next level up
7. When a sell fills → place buy at next level down

**Grid state tracking:**
```python
@dataclass
class GridState:
    symbol: str
    center_price: float
    lower_price: float
    upper_price: float
    step_pct: float
    grid_levels: list[dict]  # [{price, side, order_id, filled}]
    investment_usdt: float
    created_at: datetime
```

**Key implementation notes:**
- Grid state must be persisted to DB (or in-memory dict with DB backup) to survive restarts
- On restart: fetch open orders from Binance, reconcile with grid state
- Cancel stale grid orders if price moved beyond grid range
- Each grid level = separate limit order on Binance
- Grid step MUST be ≥ 0.5% to cover round-trip fees (0.2%)

**BinanceClient methods needed:**
- `place_limit_buy(symbol, price, qty)` — NEW, not in Phase 1
- `place_limit_sell(symbol, price, qty)` — NEW
- `get_open_orders(symbol)` — EXISTS
- `cancel_order(symbol, order_id)` — EXISTS

```python
# Add to binance_client.py
def place_limit_buy(self, symbol: str, price: float, quantity: float) -> dict:
    precision = self.quantity_precision(symbol)
    price_precision = self.price_precision(symbol)
    return self.client.create_order(
        symbol=f"{symbol}USDT",
        side=Client.SIDE_BUY,
        type=Client.ORDER_TYPE_LIMIT,
        timeInForce=Client.TIME_IN_FORCE_GTC,
        quantity=round(quantity, precision),
        price=round(price, price_precision),
    )

def place_limit_sell(self, symbol: str, price: float, quantity: float) -> dict:
    precision = self.quantity_precision(symbol)
    price_precision = self.price_precision(symbol)
    return self.client.create_order(
        symbol=f"{symbol}USDT",
        side=Client.SIDE_SELL,
        type=Client.ORDER_TYPE_LIMIT,
        timeInForce=Client.TIME_IN_FORCE_GTC,
        quantity=round(quantity, precision),
        price=round(price, price_precision),
    )
```

[VERIFIED: python-binance supports LIMIT orders with timeInForce=GTC]

**Config from config.yaml:**
```yaml
strategies:
  grid:
    grid_count: 10
    grid_step_pct: 0.8  # min 0.5%
    investment_usdt: 15
    mode: arithmetic
```

[CITED: binance-bot spec §6.1]

---

### 2. DCA (Dollar Cost Averaging) (STRAT-02)

**Spec reference:** §6.2 — НИСХОДЯЩИЙ ТРЕНД, RSI < 35

**Algorithm:**
1. Check if RSI(14) < 35 on 1h timeframe
2. If no open DCA position for this symbol → open initial buy (10 USDT)
3. If price drops `price_deviation`% (2.5%) from last buy → buy more
4. Track all buys: quantity, price, total cost
5. Calculate average entry: `total_cost / total_quantity`
6. When current price ≥ average_entry * (1 + take_profit_net/100) → sell all
7. When drawdown from average ≥ stop_loss → sell all (stop-loss)

**DCA position tracking:**
```python
@dataclass
class DCAPosition:
    symbol: str
    buys: list[dict]  # [{price, quantity, timestamp, order_id}]
    total_quantity: float
    total_cost: float
    avg_entry: float
    orders_count: int
    max_orders: int  # 5
    last_buy_price: float
```

**Key implementation notes:**
- DCA uses market orders (not limit) — price deviation triggers market buy
- Average entry = `sum(buy_price * qty) / sum(qty)` — includes fees in cost
- Take profit is NET of fees: need `current_price * qty * (1 - FEE_RATE) > total_cost * (1 + take_profit_pct/100)`
- Stop loss is also net: sell when loss exceeds threshold

**Net PnL calculation for DCA exit:**
```python
def calc_dca_exit_pnl(dca_pos: DCAPosition, current_price: float) -> dict:
    sell_total = current_price * dca_pos.total_quantity
    fee_sell = sell_total * FEE_RATE
    net_sell = sell_total - fee_sell
    net_pnl = net_sell - dca_pos.total_cost
    net_pnl_pct = net_pnl / dca_pos.total_cost * 100
    return {
        "net_pnl": round(net_pnl, 4),
        "net_pnl_pct": round(net_pnl_pct, 3),
        "fee_total": round(dca_pos.total_cost * FEE_RATE + fee_sell, 4),
    }
```

**Config:**
```yaml
strategies:
  dca:
    amount_per_buy: 10  # USDT
    max_orders: 5
    price_deviation: 2.5  # %
    take_profit_net: 1.8  # %
    stop_loss: 12.0  # %
```

[CITED: binance-bot spec §6.2]

---

### 3. RSI + EMA Strategy (STRAT-03)

**Spec reference:** §6.3 — ТЕХНИЧЕСКИЙ ТРЕНД, ADX 20–35

**Algorithm:**
1. Fetch 200+ 1h klines
2. Calculate RSI(14) and EMA(200)
3. **Buy signal:** RSI < 35 (oversold) AND current_price > EMA200 (uptrend filter)
4. **Sell signal:** RSI > 65 (overbought) OR current_price < EMA200 (trend break)
5. Place market buy/sell
6. Set take_profit at entry * (1 + 2.0/100)
7. Set stop_loss at entry * (1 - 2.5/100)

**pandas-ta indicator calculation:**
```python
import pandas as pd
import pandas_ta as ta

def calc_indicators(klines: list[dict]) -> dict:
    df = pd.DataFrame(klines)
    df["rsi"] = ta.rsi(df["close"], length=14)
    df["ema200"] = ta.ema(df["close"], length=200)
    df["adx"] = ta.adx(df["high"], df["low"], df["close"], length=14)["ADX_14"]
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)

    latest = df.iloc[-1]
    return {
        "rsi": latest["rsi"],
        "ema200": latest["ema200"],
        "adx": latest["adx"],
        "atr": latest["atr"],
        "atr_pct": latest["atr"] / latest["close"] * 100,
    }
```

[VERIFIED: pandas-ta.rsi, pandas-ta.ema, pandas-ta.adx, pandas-ta.atr exist]

**Key implementation notes:**
- EMA200 requires at least 200 klines — fetch `limit=250` to be safe
- RSI and EMA are calculated on close prices
- ADX is from the same library call — reuse for AutoSelector
- Take profit/stop loss are checked on each tick by comparing current price to entry

**Config:**
```yaml
strategies:
  rsi_ema:
    rsi_period: 14
    rsi_oversold: 35
    rsi_overbought: 65
    ema_period: 200
    timeframe: "1h"
    position_size: 15  # USDT
    take_profit_net: 2.0  # %
    stop_loss: 2.5  # %
```

[CITED: binance-bot spec §6.3]

---

### 4. Multi-Timeframe Momentum (STRAT-04)

**Spec reference:** §6.4 — СИЛЬНЫЙ ТРЕНД, ADX > 35

**Algorithm:**
1. Fetch klines for 3 timeframes: 4h, 1h, 15m
2. Calculate RSI(14) on each timeframe
3. Calculate EMA(50) on each timeframe for trend direction
4. **Buy signal:** ADX(4h) > 35 AND RSI(4h) > 50 AND RSI(1h) > 50 AND RSI(15m) > 50
5. **Sell signal:** RSI(15m) < 40 (weakening momentum)
6. Trailing stop: track highest price since entry, stop at `highest * (1 - 2.0/100)`

**Multi-timeframe fetch:**
```python
def fetch_multi_tf_klines(binance, symbol: str) -> dict:
    """Fetch klines for all 3 timeframes."""
    klines = {}
    for tf in ["4h", "1h", "15m"]:
        raw = binance.client.get_klines(
            symbol=f"{symbol}USDT",
            interval=tf,
            limit=200,
        )
        klines[tf] = [{
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        } for k in raw]
    return klines
```

**Trailing stop state:**
```python
@dataclass
class TrailingStopState:
    symbol: str
    entry_price: float
    highest_since_entry: float
    trailing_pct: float  # 2.0%
    stop_price: float  # highest * (1 - trailing_pct/100)
```

**Key implementation notes:**
- 15m klines change fast — tick interval should be ≤ 5 minutes
- Trailing stop updates on every tick: if price > highest → update highest → recalc stop
- ADX from 4h timeframe is the primary filter
- All 3 RSI values must agree for entry (conservative)

**Config:**
```yaml
strategies:
  mtf:
    timeframes: ["4h", "1h", "15m"]
    position_size: 15  # USDT
    take_profit_net: 3.5  # %
    stop_loss: 2.0  # %
    trailing_stop: true
    trailing_pct: 2.0  # %
    adx_threshold: 35
```

[CITED: binance-bot spec §6.4]

---

## AutoSelector Logic (STRAT-05)

**Spec reference:** §6.5

The AutoSelector examines market conditions and routes to the best strategy:

```python
class AutoSelector:
    """Selects strategy based on market conditions."""

    def select(self, indicators: dict) -> str:
        adx = indicators["adx"]
        rsi = indicators["rsi"]
        atr_pct = indicators["atr_pct"]

        if adx < 20:
            return "grid"  # Range-bound market
        elif adx < 35:
            if rsi < 35:
                return "dca"  # Downtrend, accumulate
            else:
                return "rsi_ema"  # Trend with corrections
        else:  # adx >= 35
            return "mtf"  # Strong trend
```

**Decision matrix (from spec):**

| ADX Range | RSI Condition | Strategy |
|-----------|---------------|----------|
| ADX < 20 | Any | Grid |
| 20 ≤ ADX < 35 | RSI < 35 | DCA |
| 20 ≤ ADX < 35 | RSI ≥ 35 | RSI+EMA |
| ADX ≥ 35 | Any | MTF Momentum |

**Indicator calculation for AutoSelector:**
```python
def get_market_indicators(binance, symbol: str) -> dict:
    raw = binance.client.get_klines(
        symbol=f"{symbol}USDT",
        interval="1h",
        limit=200,
    )
    klines = [{
        "open": float(k[1]),
        "high": float(k[2]),
        "low": float(k[3]),
        "close": float(k[4]),
        "volume": float(k[5]),
    } for k in raw]

    df = pd.DataFrame(klines)
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)

    return {
        "adx": adx_df["ADX_14"].iloc[-1],
        "rsi": ta.rsi(df["close"], length=14).iloc[-1],
        "atr_pct": ta.atr(df["high"], df["low"], df["close"], length=14).iloc[-1] / df["close"].iloc[-1] * 100,
    }
```

[ASSUMED: ADX-based routing is standard for multi-strategy systems]

**Key implementation notes:**
- AutoSelector runs on every tick BEFORE the active strategy
- If market conditions change (ADX crosses threshold), switch strategy
- Preserve open positions during strategy switch — don't close them
- Log strategy switches for transparency

---

## Risk Manager Implementation (RISK-01..04)

### Requirements

| ID | Rule | Value |
|----|------|-------|
| RISK-01 | Max open positions | 7 |
| RISK-02 | Daily loss limit | 5% of capital |
| RISK-03 | USDT reserve buffer | 20 USDT |
| RISK-04 | Cooldown after stop-loss | 15 minutes |

[CITED: binance-bot spec REQUIREMENTS.md]

### Implementation

```python
# src/core/risk_manager.py
from datetime import datetime, timedelta
from loguru import logger
from src.core.constants import (
    MAX_OPEN_POSITIONS,
    RESERVED_USDT,
    FEE_RATE,
)
from src.core.capital import get_capital_info
from src.database.session import SessionLocal
from src.database.models import Trade


class RiskManager:
    """Enforces risk limits before every trade."""

    DAILY_LOSS_LIMIT_PCT = 5.0  # %
    COOLDOWN_MINUTES = 15

    def __init__(self):
        self._cooldown_until: dict[str, datetime] = {}  # symbol -> datetime

    def can_trade(self, symbol: str) -> tuple[bool, str]:
        """Check all risk conditions. Returns (allowed, reason)."""

        # RISK-01: Max positions
        open_count = self._count_open_positions()
        if open_count >= MAX_OPEN_POSITIONS:
            return False, f"Max positions reached ({MAX_OPEN_POSITIONS})"

        # RISK-02: Daily loss limit
        daily_pnl = self._get_daily_pnl()
        capital_info = get_capital_info()
        if capital_info:
            daily_limit = capital_info["starting_capital"] * self.DAILY_LOSS_LIMIT_PCT / 100
            if daily_pnl < -daily_limit:
                return False, f"Daily loss limit reached ({daily_pnl:.2f} / -{daily_limit:.2f})"

        # RISK-03: Reserve buffer
        balance = self._get_available_balance()
        if balance < RESERVED_USDT:
            return False, f"Reserve buffer: {balance:.2f} < {RESERVED_USDT} USDT"

        # RISK-04: Cooldown
        if symbol in self._cooldown_until:
            if datetime.utcnow() < self._cooldown_until[symbol]:
                remaining = (self._cooldown_until[symbol] - datetime.utcnow()).seconds // 60
                return False, f"Cooldown: {remaining} min remaining for {symbol}"

        return True, "OK"

    def trigger_cooldown(self, symbol: str):
        """Start cooldown after stop-loss."""
        self._cooldown_until[symbol] = datetime.utcnow() + timedelta(
            minutes=self.COOLDOWN_MINUTES
        )
        logger.info(f"RiskManager: cooldown started for {symbol} until {self._cooldown_until[symbol]}")

    def _count_open_positions(self) -> int:
        db = SessionLocal()
        try:
            return db.query(Trade).filter(Trade.status == "OPEN").count()
        finally:
            db.close()

    def _get_daily_pnl(self) -> float:
        """Sum of net_pnl for trades closed today."""
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

    def _get_available_balance(self) -> float:
        """Current USDT balance minus reserved buffer."""
        capital_info = get_capital_info()
        if not capital_info:
            return 0.0
        return capital_info["current_balance"] - RESERVED_USDT
```

[ASSUMED: Standard risk manager pattern with daily tracking]

### Drawdown Circuit Breaker

```python
def check_drawdown(self) -> bool:
    """Returns True if drawdown > 8% — should stop trading."""
    capital_info = get_capital_info()
    if not capital_info:
        return False
    if capital_info["drawdown_pct"] > 8.0:
        logger.warning(f"RiskManager: drawdown {capital_info['drawdown_pct']:.2f}% > 8% — STOP TRADING")
        return True
    return False
```

[CITED: binance-bot spec §6.4 Anomaly Guard]

### PnL Net of Fees

**Critical rule:** All PnL calculations MUST subtract fees. Use the existing `calc_pnl()` from `src/core/capital.py`:

```python
from src.core.capital import calc_pnl

# When closing a position:
pnl = calc_pnl(buy_price=entry_price, sell_price=current_price, qty=quantity)
# pnl["net_pnl"] is after fees
# pnl["net_pnl_pct"] is percentage after fees
```

[VERIFIED: calc_pnl exists in src/core/capital.py:81]

---

## APScheduler Integration

### Strategy Tick Job

```python
# In src/main.py — add after Telegram bot setup
from apscheduler.schedulers.background import BackgroundScheduler

def setup_scheduler(strategy_manager):
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=strategy_manager.tick_all,
        trigger="interval",
        minutes=5,
        misfire_grace_time=60,
        id="strategy_tick",
    )
    scheduler.start()
    return scheduler
```

[VERIFIED: APScheduler BackgroundScheduler supports interval triggers]

### Thread Safety

- APScheduler `BackgroundScheduler` runs jobs in thread pool
- `BinanceClient` uses sync `Client` — safe to call from any thread (GIL protects)
- SQLite sessions must NOT be shared across threads — create `SessionLocal()` per call
- Strategy state (grid levels, DCA positions) needs thread-safe access or per-tick isolation

**Pattern:**
```python
class StrategyManager:
    def tick_all(self):
        """Called by APScheduler in background thread."""
        pairs = self.config["trading_pairs"]["core"]
        for symbol in pairs:
            try:
                self.tick(symbol)
            except Exception as e:
                logger.error(f"Strategy tick failed for {symbol}: {e}")
```

[ASSUMED: Standard APScheduler thread safety pattern]

### Tick Interval

| Strategy | Recommended Tick | Rationale |
|----------|-----------------|-----------|
| Grid | 5 min | Check limit order fills |
| DCA | 5 min | Check price deviation |
| RSI+EMA | 5 min | Check RSI/EMA signals |
| MTF | 5 min | 15m candles need frequent checks |

**Use 5 minutes as universal tick interval.** [ASSUMED]

---

## Common Pitfalls

### pandas-ta

1. **Minimum data length**: EMA(200) needs 200+ data points. Always fetch `limit=250` klines. [VERIFIED: pandas-ta docs]
2. **NaN values**: First N rows will be NaN (where N = indicator period). Use `.dropna()` or check with `.iloc[-1]` after enough data. [ASSUMED: standard pandas-ta behavior]
3. **DataFrame format**: pandas-ta works on pandas DataFrames with columns `open, high, low, close, volume`. Match the column names exactly. [VERIFIED: pandas-ta examples]
4. **ADX returns DataFrame**: `ta.adx()` returns a DataFrame with columns `ADX_14`, `DMP_14`, `DMN_14`. Access `["ADX_14"]` specifically. [VERIFIED: pandas-ta ADX docs]

### Grid Trading

1. **Limit order fills are not guaranteed**: Price may never reach your grid levels. Grid works best in range-bound markets. [ASSUMED: basic limit order behavior]
2. **Grid state persistence**: If bot restarts, grid orders remain on Binance but bot loses track. Must reconcile on startup by fetching open orders. [ASSUMED: critical for grid reliability]
3. **Grid step too small**: If step < 0.2%, fees eat all profit. Minimum 0.5% per spec. [CITED: binance-bot spec §6.1]

### DCA

1. **Average entry includes fees**: When calculating average entry, include buy fees in the cost basis. [ASSUMED: correct DCA accounting]
2. **Max orders hard limit**: Never exceed `max_orders` (5). Track count in state. [CITED: binance-bot spec §6.2]

### Multi-Timeframe

1. **Timezone awareness**: Binance kline timestamps are UTC milliseconds. pandas-ta doesn't care about timezone but be consistent. [ASSUMED]
2. **15m kline data freshness**: 15m candles update every 15 minutes. A tick at minute 14 sees almost-stale data. [ASSUMED]

### Risk Manager

1. **Daily PnL reset**: Daily loss limit resets at midnight UTC. Use `datetime.utcnow().replace(hour=0, ...)`. [ASSUMED: standard daily reset]
2. **Cooldown is per-symbol**: Stop-loss on BTC doesn't block ETH trading. [ASSUMED: per-symbol cooldown]

---

## Code Examples

### Complete Strategy Tick Flow

```python
# src/strategies/manager.py
from loguru import logger
from src.strategies.base import Signal
from src.core.risk_manager import RiskManager
from src.indicators import calc_indicators

class StrategyManager:
    def __init__(self, binance, config):
        self.binance = binance
        self.config = config
        self.strategies = {}
        self.active_name = None
        self.risk_manager = RiskManager()

    def register(self, name, strategy):
        self.strategies[name] = strategy

    def set_active(self, name):
        self.active_name = name
        logger.info(f"Strategy set to: {name}")

    def tick_all(self):
        pairs = self.config["trading_pairs"]["core"]
        for symbol in pairs:
            try:
                self.tick(symbol)
            except Exception as e:
                logger.error(f"Tick failed for {symbol}: {e}")

    def tick(self, symbol: str):
        # 1. Risk check
        can_trade, reason = self.risk_manager.can_trade(symbol)
        if not can_trade:
            logger.debug(f"Risk blocked {symbol}: {reason}")
            return

        # 2. Fetch data
        klines_raw = self.binance.client.get_klines(
            symbol=f"{symbol}USDT", interval="1h", limit=250
        )
        klines = [{
            "open": float(k[1]), "high": float(k[2]),
            "low": float(k[3]), "close": float(k[4]),
            "volume": float(k[5]),
        } for k in klines_raw]

        current_price = self.binance.get_price(symbol)
        indicators = calc_indicators(klines)

        # 3. Get active strategy
        strategy = self.strategies.get(self.active_name)
        if not strategy:
            return

        # 4. Analyze
        open_positions = self._get_open_positions(symbol)
        action = strategy.analyze(symbol, klines, current_price, open_positions)

        # 5. Execute
        if action.signal == Signal.BUY:
            self._execute_buy(action, symbol)
        elif action.signal == Signal.SELL:
            self._execute_sell(action, symbol)
```

### Indicator Calculation Module

```python
# src/indicators/__init__.py
import pandas as pd
import pandas_ta as ta


def calc_indicators(klines: list[dict]) -> dict:
    """Calculate all indicators from kline data."""
    df = pd.DataFrame(klines)

    rsi = ta.rsi(df["close"], length=14)
    ema200 = ta.ema(df["close"], length=200)
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)

    return {
        "rsi": float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0,
        "ema200": float(ema200.iloc[-1]) if not pd.isna(ema200.iloc[-1]) else df["close"].iloc[-1],
        "adx": float(adx_df["ADX_14"].iloc[-1]) if not pd.isna(adx_df["ADX_14"].iloc[-1]) else 20.0,
        "atr": float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0,
        "atr_pct": float(atr.iloc[-1] / df["close"].iloc[-1] * 100) if not pd.isna(atr.iloc[-1]) else 0.0,
    }


def calc_rsi(klines: list[dict], period: int = 14) -> float:
    df = pd.DataFrame(klines)
    rsi = ta.rsi(df["close"], length=period)
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
```

### Config Loading for Strategies

```python
# Load strategy params from config.yaml
import yaml

def load_strategy_config() -> dict:
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    return config.get("strategies", {})
```

**config.yaml additions:**
```yaml
strategies:
  grid:
    grid_count: 10
    grid_step_pct: 0.8
    investment_usdt: 15
    mode: arithmetic

  dca:
    amount_per_buy: 10
    max_orders: 5
    price_deviation: 2.5
    take_profit_net: 1.8
    stop_loss: 12.0

  rsi_ema:
    rsi_period: 14
    rsi_oversold: 35
    rsi_overbought: 65
    ema_period: 200
    timeframe: "1h"
    position_size: 15
    take_profit_net: 2.0
    stop_loss: 2.5

  mtf:
    timeframes: ["4h", "1h", "15m"]
    position_size: 15
    take_profit_net: 3.5
    stop_loss: 2.0
    trailing_stop: true
    trailing_pct: 2.0
    adx_threshold: 35
```

---

## Provenance Index

| Claim | Source |
|-------|--------|
| pandas-ta supports RSI, EMA, ATR, ADX | [VERIFIED: pypi.org/project/pandas-ta] |
| python-binance supports LIMIT orders with timeInForce | [VERIFIED: python-binance Client.create_order docs] |
| APScheduler BackgroundScheduler supports interval triggers | [VERIFIED: APScheduler docs] |
| EMA(200) requires 200+ data points | [ASSUMED: standard EMA calculation] |
| Grid step minimum 0.5% | [CITED: binance-bot spec §6.1] |
| DCA take_profit_net 1.8% | [CITED: binance-bot spec §6.2] |
| RSI+EMA take_profit_net 2.0% | [CITED: binance-bot spec §6.3] |
| MTF take_profit_net 3.5% | [CITED: binance-bot spec §6.4] |
| Max 7 open positions | [CITED: REQUIREMENTS.md RISK-01] |
| Daily loss limit 5% | [CITED: REQUIREMENTS.md RISK-02] |
| 20 USDT reserve buffer | [CITED: REQUIREMENTS.md RISK-03] |
| 15-min cooldown after stop-loss | [CITED: REQUIREMENTS.md RISK-04] |
| FEE_RATE = 0.001 (0.1%) | [VERIFIED: src/core/constants.py] |
| calc_pnl() handles fee deduction | [VERIFIED: src/core/capital.py:81] |
| Symbol conversion: API uses BTCUSDT, DB uses BTC | [CITED: binance-bot spec §9, binance_client.py] |
| quantity_precision/price_precision needed for orders | [VERIFIED: src/core/binance_client.py:47-61] |
| BackgroundScheduler is thread-based (not async) | [CITED: APScheduler docs] |
| SQLite sessions must be per-thread | [ASSUMED: SQLite thread safety] |

---

*Research completed: 2026-06-16*
