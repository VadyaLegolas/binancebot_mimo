---
wave: 1
depends_on: []
files_modified:
  - src/strategies/__init__.py
  - src/strategies/base.py
  - src/strategies/grid.py
  - src/indicators/__init__.py
  - src/core/binance_client.py
  - config.yaml
  - requirements.txt
requirements_addressed:
  - STRAT-01
autonomous: true
---

# Plan 1 — Strategy Base + Indicators + Grid

<objective>
Build the strategy plugin architecture and first working strategy (Grid). This plan creates the abstract base class, the shared indicator calculation module, adds limit order methods to BinanceClient, and implements Grid Trading with state tracking. Grid must place limit buy/sell orders on Binance and reconcile fills on tick.
</objective>

---

## Task 1.1 — Add `pandas-ta` to requirements and install

<read_first>
- requirements.txt (current dependencies)
</read_first>

<action>
1. Add `pandas-ta==0.3.14b` to `requirements.txt` after the numpy line
2. Run `pip install pandas-ta==0.3.14b` to install it
</action>

<acceptance_criteria>
- `requirements.txt` contains `pandas-ta==0.3.14b`
- `pip install pandas-ta` succeeds without errors
- `python -c "import pandas_ta; print(pandas_ta.__version__)"` prints `0.3.14b`
</acceptance_criteria>

---

## Task 1.2 — Create indicator calculation module

<read_first>
- src/indicators/__init__.py (currently empty)
- src/core/capital.py (for FEE_RATE reference)
- src/core/constants.py (for FEE_RATE value)
</read_first>

<action>
1. Write `src/indicators/__init__.py` with two public functions:

```python
import pandas as pd
import pandas_ta as ta


def calc_indicators(klines: list[dict]) -> dict:
    """Calculate RSI(14), EMA(200), ADX(14), ATR(14) from kline data.
    Returns dict with keys: rsi, ema200, adx, atr, atr_pct.
    Handles NaN by falling back to safe defaults (50.0 for RSI, close price for EMA, 20.0 for ADX).
    klines must have keys: open, high, low, close, volume.
    """
    df = pd.DataFrame(klines)
    rsi = ta.rsi(df["close"], length=14)
    ema200 = ta.ema(df["close"], length=200)
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)

    last_close = float(df["close"].iloc[-1])
    return {
        "rsi": float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0,
        "ema200": float(ema200.iloc[-1]) if not pd.isna(ema200.iloc[-1]) else last_close,
        "adx": float(adx_df["ADX_14"].iloc[-1]) if not pd.isna(adx_df["ADX_14"].iloc[-1]) else 20.0,
        "atr": float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0.0,
        "atr_pct": float(atr.iloc[-1] / last_close * 100) if not pd.isna(atr.iloc[-1]) else 0.0,
    }


def calc_rsi(klines: list[dict], period: int = 14) -> float:
    """Calculate RSI for a given period. Returns float, defaults to 50.0 on NaN."""
    df = pd.DataFrame(klines)
    rsi = ta.rsi(df["close"], length=period)
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0
```
</action>

<acceptance_criteria>
- `from src.indicators import calc_indicators, calc_rsi` works without ImportError
- `calc_indicators([{k: 1.0 for k in ["open","high","low","close","volume"]} for _ in range(250)])` returns dict with keys rsi, ema200, adx, atr, atr_pct
- All returned values are floats, no NaN
</acceptance_criteria>

---

## Task 1.3 — Create strategy base class

<read_first>
- src/strategies/__init__.py (currently empty)
- binance_bot_spec_v2.md §6 (strategy specs)
- 02-RESEARCH.md "Strategy Architecture" section (BaseStrategy pattern)
</read_first>

<action>
1. Write `src/strategies/base.py` with:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
    name: str = "base"

    @abstractmethod
    def analyze(self, symbol: str, klines: list[dict], current_price: float,
                open_positions: list) -> TradeAction:
        ...

    @abstractmethod
    def get_params(self) -> dict:
        ...

    @abstractmethod
    def set_params(self, params: dict) -> None:
        ...

    def on_fill(self, symbol: str, side: str, price: float, quantity: float) -> None:
        """Hook called when an order fill is detected. Override in subclasses."""
        pass
```
</action>

<acceptance_criteria>
- `from src.strategies.base import BaseStrategy, Signal, TradeAction` works
- BaseStrategy is abstract — instantiating it directly raises TypeError
- TradeAction dataclass can be constructed with all fields
</acceptance_criteria>

---

## Task 1.4 — Add limit order methods to BinanceClient

<read_first>
- src/core/binance_client.py (current implementation, lines 70-98 for market orders)
</read_first>

<action>
1. Add two methods to `BinanceClient` class, after `place_market_sell` (after line 97):

```python
    def place_limit_buy(self, symbol: str, price: float, quantity: float) -> dict:
        try:
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
        except BinanceAPIException as e:
            logger.error(f"Binance API error placing limit buy for {symbol}: {e.status_code} - {e.message}")
            raise

    def place_limit_sell(self, symbol: str, price: float, quantity: float) -> dict:
        try:
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
        except BinanceAPIException as e:
            logger.error(f"Binance API error placing limit sell for {symbol}: {e.status_code} - {e.message}")
            raise
```
</action>

<acceptance_criteria>
- `BinanceClient` has methods `place_limit_buy` and `place_limit_sell`
- Both accept symbol, price, quantity and return dict
- Both use TIME_IN_FORCE_GTC and round to correct precision
- No existing methods are broken
</acceptance_criteria>

---

## Task 1.5 — Create Grid Trading strategy

<read_first>
- src/strategies/base.py (BaseStrategy, Signal, TradeAction)
- src/core/binance_client.py (place_limit_buy, place_limit_sell, get_open_orders, cancel_order, get_price, quantity_precision, price_precision)
- src/core/capital.py (calc_pnl)
- src/core/constants.py (FEE_RATE, MIN_TRADE_USDT)
- binance_bot_spec_v2.md §6.1 (Grid Trading spec)
- 02-RESEARCH.md "Grid Trading" section
- config.yaml (needs strategies.grid section)
</read_first>

<action>
1. Write `src/strategies/grid.py`:

```python
import time
from dataclasses import dataclass, field
from loguru import logger
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.core.capital import calc_pnl
from src.core.constants import FEE_RATE


@dataclass
class GridLevel:
    price: float
    side: str  # "BUY" or "SELL"
    order_id: int | None = None
    filled: bool = False
    quantity: float = 0.0


class GridStrategy(BaseStrategy):
    name = "grid"

    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        cfg = config.get("strategies", {}).get("grid", {})
        self.grid_count = cfg.get("grid_count", 10)
        self.grid_step_pct = max(cfg.get("grid_step_pct", 0.8), 0.5)
        self.investment_usdt = cfg.get("investment_usdt", 15)
        self._grids: dict[str, list[GridLevel]] = {}  # symbol -> grid levels

    def get_params(self) -> dict:
        return {
            "grid_count": self.grid_count,
            "grid_step_pct": self.grid_step_pct,
            "investment_usdt": self.investment_usdt,
        }

    def set_params(self, params: dict) -> None:
        if "grid_count" in params:
            self.grid_count = params["grid_count"]
        if "grid_step_pct" in params:
            self.grid_step_pct = max(params["grid_step_pct"], 0.5)
        if "investment_usdt" in params:
            self.investment_usdt = params["investment_usdt"]

    def analyze(self, symbol: str, klines: list[dict], current_price: float,
                open_positions: list) -> TradeAction:

        # If no grid exists for this symbol, create one
        if symbol not in self._grids or not self._grids[symbol]:
            return self._create_grid(symbol, current_price)

        # Check for filled orders and place counter-orders
        grid = self._grids[symbol]
        for level in grid:
            if level.filled or level.order_id is None:
                continue
            # Check if order is still open
            open_orders = self.binance.get_open_orders(symbol)
            open_ids = {o["orderId"] for o in open_orders}
            if level.order_id not in open_ids:
                # Order filled — place counter-order
                level.filled = True
                if level.side == "BUY":
                    # Buy filled → place sell at next level up
                    sell_price = level.price * (1 + self.grid_step_pct / 100)
                    qty = self._calc_grid_qty(sell_price)
                    if qty > 0:
                        order = self.binance.place_limit_sell(symbol, sell_price, qty)
                        grid.append(GridLevel(
                            price=sell_price, side="SELL",
                            order_id=order["orderId"], quantity=qty,
                        ))
                        logger.info(f"Grid {symbol}: BUY filled at {level.price}, placed SELL at {sell_price}")
                elif level.side == "SELL":
                    # Sell filled → place buy at next level down
                    buy_price = level.price * (1 - self.grid_step_pct / 100)
                    qty = self._calc_grid_qty(buy_price)
                    if qty > 0:
                        order = self.binance.place_limit_buy(symbol, buy_price, qty)
                        grid.append(GridLevel(
                            price=buy_price, side="BUY",
                            order_id=order["orderId"], quantity=qty,
                        ))
                        logger.info(f"Grid {symbol}: SELL filled at {level.price}, placed BUY at {buy_price}")

        return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="Grid active")

    def _create_grid(self, symbol: str, current_price: float) -> TradeAction:
        """Create initial grid of limit orders around current price."""
        from src.indicators import calc_indicators
        from src.core.constants import MIN_TRADE_USDT

        # Calculate grid range from ATR
        indicators = calc_indicators([])  # empty fallback
        atr_pct = indicators.get("atr_pct", 1.0)
        if atr_pct < 0.5:
            atr_pct = 1.0  # minimum range

        half_range = current_price * atr_pct / 100 * 2
        lower = current_price - half_range
        upper = current_price + half_range

        step_price = (upper - lower) / self.grid_count
        per_level_usdt = self.investment_usdt / self.grid_count

        grid = []
        levels_placed = 0

        for i in range(self.grid_count):
            level_price = lower + step_price * (i + 1)
            if level_price >= current_price:
                # Sell levels above current price
                qty = per_level_usdt / level_price
                if per_level_usdt >= MIN_TRADE_USDT:
                    try:
                        order = self.binance.place_limit_sell(symbol, level_price, qty)
                        grid.append(GridLevel(
                            price=level_price, side="SELL",
                            order_id=order["orderId"], quantity=qty,
                        ))
                        levels_placed += 1
                    except Exception as e:
                        logger.error(f"Grid: failed to place SELL at {level_price}: {e}")
            else:
                # Buy levels below current price
                qty = per_level_usdt / level_price
                if per_level_usdt >= MIN_TRADE_USDT:
                    try:
                        order = self.binance.place_limit_buy(symbol, level_price, qty)
                        grid.append(GridLevel(
                            price=level_price, side="BUY",
                            order_id=order["orderId"], quantity=qty,
                        ))
                        levels_placed += 1
                    except Exception as e:
                        logger.error(f"Grid: failed to place BUY at {level_price}: {e}")

        self._grids[symbol] = grid
        logger.info(f"Grid {symbol}: created {levels_placed} levels, range {lower:.2f}-{upper:.2f}, step {self.grid_step_pct}%")
        return TradeAction(signal=Signal.HOLD, symbol=symbol, reason=f"Grid created: {levels_placed} levels")

    def _calc_grid_qty(self, price: float) -> float:
        """Calculate quantity per grid level."""
        per_level_usdt = self.investment_usdt / self.grid_count
        return per_level_usdt / price

    def cancel_grid(self, symbol: str):
        """Cancel all grid orders for a symbol."""
        if symbol in self._grids:
            for level in self._grids[symbol]:
                if level.order_id and not level.filled:
                    try:
                        self.binance.cancel_order(symbol, level.order_id)
                    except Exception:
                        pass
            self._grids.pop(symbol, None)
            logger.info(f"Grid {symbol}: cancelled all orders")
```

2. Update `src/strategies/__init__.py`:

```python
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.strategies.grid import GridStrategy

ALL_STRATEGIES = {
    "grid": GridStrategy,
}
```
</action>

<acceptance_criteria>
- `from src.strategies.grid import GridStrategy` works
- GridStrategy inherits BaseStrategy
- `GridStrategy.name == "grid"`
- `get_params()` returns dict with grid_count, grid_step_pct, investment_usdt
- `set_params({"grid_step_pct": 0.5})` clamps to 0.5 minimum
- `ALL_STRATEGIES` dict in `__init__.py` contains `"grid": GridStrategy`
- Grid creates buy levels below price and sell levels above price
- Grid step is never below 0.5% (enforced in __init__ and set_params)
</acceptance_criteria>

---

## Task 1.6 — Add strategy config to config.yaml

<read_first>
- config.yaml (current content)
</read_first>

<action>
1. Append to `config.yaml`:

```yaml
strategies:
  grid:
    grid_count: 10
    grid_step_pct: 0.8
    investment_usdt: 15

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

auto_selector:
  enabled: true

risk:
  max_open_positions: 7
  daily_loss_limit_pct: 5.0
  reserved_usdt: 20
  cooldown_minutes: 15
```
</action>

<acceptance_criteria>
- `config.yaml` is valid YAML (parseable by `yaml.safe_load`)
- Contains `strategies.grid`, `strategies.dca`, `strategies.rsi_ema`, `strategies.mtf` sections
- Contains `risk` section with all 4 parameters
- Grid step_pct is 0.8 (above 0.5 minimum)
</acceptance_criteria>

---

## Artifacts this phase produces

| File | Purpose |
|------|---------|
| `src/indicators/__init__.py` | Shared indicator calculation (RSI, EMA200, ADX, ATR) |
| `src/strategies/base.py` | Abstract base class, Signal enum, TradeAction dataclass |
| `src/strategies/grid.py` | Grid Trading strategy with limit order placement and fill tracking |
| `src/strategies/__init__.py` | Strategy registry (ALL_STRATEGIES dict) |
| `src/core/binance_client.py` | Extended with place_limit_buy, place_limit_sell |
| `config.yaml` | Strategy parameters and risk settings added |
| `requirements.txt` | pandas-ta added |
