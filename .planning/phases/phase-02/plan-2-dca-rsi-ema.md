---
wave: 2
depends_on:
  - plan-1-base-indicators-grid.md
files_modified:
  - src/strategies/dca.py
  - src/strategies/rsi_ema.py
  - src/strategies/__init__.py
requirements_addressed:
  - STRAT-02
  - STRAT-03
autonomous: true
---

# Plan 2 — DCA + RSI/EMA Strategies

<objective>
Implement DCA and RSI+EMA strategies. Both must use `calc_pnl()` from `capital.py` for all PnL calculations (net of fees). DCA accumulates on price drops and sells at take_profit_net. RSI+EMA uses oversold/overbought signals filtered by EMA200 trend.
</objective>

---

## Task 2.1 — Create DCA strategy

<read_first>
- src/strategies/base.py (BaseStrategy, Signal, TradeAction)
- src/core/binance_client.py (place_market_buy, place_market_sell, get_price)
- src/core/capital.py (calc_pnl — lines 81-95)
- src/core/constants.py (FEE_RATE, MIN_TRADE_USDT)
- binance_bot_spec_v2.md §6.2 (DCA spec)
- 02-RESEARCH.md "DCA" section (algorithm and DCAPosition dataclass)
- config.yaml (strategies.dca section)
</read_first>

<action>
1. Write `src/strategies/dca.py`:

```python
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.core.capital import calc_pnl
from src.core.constants import FEE_RATE, MIN_TRADE_USDT
from src.indicators import calc_rsi


@dataclass
class DCAPosition:
    symbol: str
    buys: list = field(default_factory=list)  # [{price, quantity, timestamp, order_id}]
    total_quantity: float = 0.0
    total_cost: float = 0.0
    avg_entry: float = 0.0
    orders_count: int = 0
    max_orders: int = 5
    last_buy_price: float = 0.0


class DCAStrategy(BaseStrategy):
    name = "dca"

    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        cfg = config.get("strategies", {}).get("dca", {})
        self.amount_per_buy = cfg.get("amount_per_buy", 10)
        self.max_orders = cfg.get("max_orders", 5)
        self.price_deviation = cfg.get("price_deviation", 2.5)
        self.take_profit_net = cfg.get("take_profit_net", 1.8)
        self.stop_loss = cfg.get("stop_loss", 12.0)
        self._positions: dict[str, DCAPosition] = {}

    def get_params(self) -> dict:
        return {
            "amount_per_buy": self.amount_per_buy,
            "max_orders": self.max_orders,
            "price_deviation": self.price_deviation,
            "take_profit_net": self.take_profit_net,
            "stop_loss": self.stop_loss,
        }

    def set_params(self, params: dict) -> None:
        for key in ("amount_per_buy", "max_orders", "price_deviation", "take_profit_net", "stop_loss"):
            if key in params:
                setattr(self, key, params[key])

    def analyze(self, symbol: str, klines: list[dict], current_price: float,
                open_positions: list) -> TradeAction:

        rsi = calc_rsi(klines)

        # Check existing position first
        if symbol in self._positions and self._positions[symbol].orders_count > 0:
            pos = self._positions[symbol]

            # Take profit check (net of fees)
            if pos.avg_entry > 0:
                pnl = calc_pnl(pos.avg_entry, current_price, pos.total_quantity)
                if pnl["net_pnl_pct"] >= self.take_profit_net:
                    # Sell all
                    qty = pos.total_quantity
                    self._positions.pop(symbol, None)
                    logger.info(f"DCA {symbol}: TAKE PROFIT at {current_price}, net PnL {pnl['net_pnl_pct']:.2f}%")
                    return TradeAction(
                        signal=Signal.SELL, symbol=symbol, quantity=qty,
                        reason=f"DCA take profit: {pnl['net_pnl_pct']:.2f}%",
                    )

                # Stop loss check (net of fees)
                if pnl["net_pnl_pct"] <= -self.stop_loss:
                    qty = pos.total_quantity
                    self._positions.pop(symbol, None)
                    logger.info(f"DCA {symbol}: STOP LOSS at {current_price}, net PnL {pnl['net_pnl_pct']:.2f}%")
                    return TradeAction(
                        signal=Signal.SELL, symbol=symbol, quantity=qty,
                        reason=f"DCA stop loss: {pnl['net_pnl_pct']:.2f}%",
                    )

            # Check for additional buy (price deviation trigger)
            if pos.orders_count < pos.max_orders and pos.last_buy_price > 0:
                drop_pct = (pos.last_buy_price - current_price) / pos.last_buy_price * 100
                if drop_pct >= self.price_deviation:
                    return self._execute_buy(symbol, current_price)

            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="DCA holding")

        # No position — check if RSI is oversold to start DCA
        if rsi < 35:
            return self._execute_buy(symbol, current_price)

        return TradeAction(signal=Signal.HOLD, symbol=symbol, reason=f"DCA waiting (RSI={rsi:.1f})")

    def _execute_buy(self, symbol: str, current_price: float) -> TradeAction:
        """Place market buy and update DCA position."""
        if symbol not in self._positions:
            self._positions[symbol] = DCAPosition(
                symbol=symbol, max_orders=self.max_orders,
            )

        pos = self._positions[symbol]
        if pos.orders_count >= pos.max_orders:
            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="DCA max orders reached")

        # Calculate quantity including fee in cost
        fee = self.amount_per_buy * FEE_RATE
        net_usdt = self.amount_per_buy - fee
        qty = net_usdt / current_price

        if self.amount_per_buy < MIN_TRADE_USDT:
            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="DCA below min trade")

        # Update position tracking
        pos.buys.append({
            "price": current_price,
            "quantity": qty,
            "timestamp": datetime.utcnow().isoformat(),
            "cost_usdt": self.amount_per_buy,
        })
        pos.total_quantity += qty
        pos.total_cost += self.amount_per_buy  # includes fee
        pos.avg_entry = pos.total_cost / pos.total_quantity
        pos.orders_count += 1
        pos.last_buy_price = current_price

        logger.info(f"DCA {symbol}: BUY #{pos.orders_count} at {current_price}, qty={qty:.6f}, avg_entry={pos.avg_entry:.2f}")
        return TradeAction(
            signal=Signal.BUY, symbol=symbol, quote_qty=self.amount_per_buy,
            reason=f"DCA buy #{pos.orders_count}",
        )

    def get_position(self, symbol: str) -> DCAPosition | None:
        return self._positions.get(symbol)
```

2. Update `src/strategies/__init__.py` to add DCA:

```python
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.strategies.grid import GridStrategy
from src.strategies.dca import DCAStrategy

ALL_STRATEGIES = {
    "grid": GridStrategy,
    "dca": DCAStrategy,
}
```
</action>

<acceptance_criteria>
- `from src.strategies.dca import DCAStrategy` works
- DCAStrategy inherits BaseStrategy
- `DCAStrategy.name == "dca"`
- get_params() returns dict with amount_per_buy, max_orders, price_deviation, take_profit_net, stop_loss
- set_params() updates all fields
- DCA triggers buy when RSI < 35 and no position exists
- DCA triggers additional buy when price drops >= price_deviation% from last buy
- DCA triggers sell when net_pnl_pct >= take_profit_net (using calc_pnl)
- DCA triggers sell when net_pnl_pct <= -stop_loss (using calc_pnl)
- DCA respects max_orders limit
- avg_entry includes fees in cost basis
- ALL_STRATEGIES contains "dca"
</acceptance_criteria>

---

## Task 2.2 — Create RSI+EMA strategy

<read_first>
- src/strategies/base.py (BaseStrategy, Signal, TradeAction)
- src/core/binance_client.py (place_market_buy, place_market_sell, get_price)
- src/core/capital.py (calc_pnl — lines 81-95)
- src/core/constants.py (FEE_RATE, MIN_TRADE_USDT)
- src/indicators/__init__.py (calc_indicators)
- binance_bot_spec_v2.md §6.3 (RSI+EMA spec)
- 02-RESEARCH.md "RSI + EMA Strategy" section
- config.yaml (strategies.rsi_ema section)
</read_first>

<action>
1. Write `src/strategies/rsi_ema.py`:

```python
from dataclasses import dataclass
from loguru import logger
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.core.capital import calc_pnl
from src.core.constants import FEE_RATE, MIN_TRADE_USDT


@dataclass
class RSIEMAPosition:
    symbol: str
    entry_price: float
    quantity: float
    cost_usdt: float
    take_profit_price: float
    stop_loss_price: float


class RSIEMAStrategy(BaseStrategy):
    name = "rsi_ema"

    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        cfg = config.get("strategies", {}).get("rsi_ema", {})
        self.rsi_period = cfg.get("rsi_period", 14)
        self.rsi_oversold = cfg.get("rsi_oversold", 35)
        self.rsi_overbought = cfg.get("rsi_overbought", 65)
        self.ema_period = cfg.get("ema_period", 200)
        self.position_size = cfg.get("position_size", 15)
        self.take_profit_net = cfg.get("take_profit_net", 2.0)
        self.stop_loss = cfg.get("stop_loss", 2.5)
        self._positions: dict[str, RSIEMAPosition] = {}

    def get_params(self) -> dict:
        return {
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "ema_period": self.ema_period,
            "position_size": self.position_size,
            "take_profit_net": self.take_profit_net,
            "stop_loss": self.stop_loss,
        }

    def set_params(self, params: dict) -> None:
        for key in ("rsi_period", "rsi_oversold", "rsi_overbought", "ema_period",
                     "position_size", "take_profit_net", "stop_loss"):
            if key in params:
                setattr(self, key, params[key])

    def analyze(self, symbol: str, klines: list[dict], current_price: float,
                open_positions: list) -> TradeAction:

        from src.indicators import calc_indicators
        indicators = calc_indicators(klines)
        rsi = indicators["rsi"]
        ema200 = indicators["ema200"]

        # Check existing position
        if symbol in self._positions:
            pos = self._positions[symbol]
            pnl = calc_pnl(pos.entry_price, current_price, pos.quantity)

            # Take profit (net of fees)
            if pnl["net_pnl_pct"] >= self.take_profit_net:
                self._positions.pop(symbol, None)
                logger.info(f"RSI+EMA {symbol}: TAKE PROFIT at {current_price}, net {pnl['net_pnl_pct']:.2f}%")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"RSI+EMA TP: {pnl['net_pnl_pct']:.2f}%",
                )

            # Stop loss (net of fees)
            if pnl["net_pnl_pct"] <= -self.stop_loss:
                self._positions.pop(symbol, None)
                logger.info(f"RSI+EMA {symbol}: STOP LOSS at {current_price}, net {pnl['net_pnl_pct']:.2f}%")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"RSI+EMA SL: {pnl['net_pnl_pct']:.2f}%",
                )

            # Sell on overbought or trend break
            if rsi > self.rsi_overbought or current_price < ema200:
                self._positions.pop(symbol, None)
                logger.info(f"RSI+EMA {symbol}: SELL signal (RSI={rsi:.1f}, price vs EMA200)")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"RSI+EMA exit: RSI={rsi:.1f}",
                )

            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="RSI+EMA holding")

        # No position — check for buy signal
        if rsi < self.rsi_oversold and current_price > ema200:
            # Oversold + above EMA200 = uptrend with correction
            if self.position_size < MIN_TRADE_USDT:
                return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="RSI+EMA below min trade")

            fee = self.position_size * FEE_RATE
            net_usdt = self.position_size - fee
            qty = net_usdt / current_price

            tp_price = current_price * (1 + self.take_profit_net / 100)
            sl_price = current_price * (1 - self.stop_loss / 100)

            self._positions[symbol] = RSIEMAPosition(
                symbol=symbol, entry_price=current_price, quantity=qty,
                cost_usdt=self.position_size,
                take_profit_price=tp_price, stop_loss_price=sl_price,
            )

            logger.info(f"RSI+EMA {symbol}: BUY at {current_price}, RSI={rsi:.1f}, EMA200={ema200:.2f}")
            return TradeAction(
                signal=Signal.BUY, symbol=symbol, quote_qty=self.position_size,
                reason=f"RSI+EMA entry: RSI={rsi:.1f}, price>EMA200",
            )

        return TradeAction(
            signal=Signal.HOLD, symbol=symbol,
            reason=f"RSI+EMA waiting (RSI={rsi:.1f}, EMA200={ema200:.2f})",
        )

    def get_position(self, symbol: str) -> RSIEMAPosition | None:
        return self._positions.get(symbol)
```

2. Update `src/strategies/__init__.py` to add RSI+EMA:

```python
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.strategies.grid import GridStrategy
from src.strategies.dca import DCAStrategy
from src.strategies.rsi_ema import RSIEMAStrategy

ALL_STRATEGIES = {
    "grid": GridStrategy,
    "dca": DCAStrategy,
    "rsi_ema": RSIEMAStrategy,
}
```
</action>

<acceptance_criteria>
- `from src.strategies.rsi_ema import RSIEMAStrategy` works
- RSIEMAStrategy inherits BaseStrategy
- `RSIEMAStrategy.name == "rsi_ema"`
- get_params() returns dict with all 7 parameters
- Buy signal: RSI < rsi_oversold AND current_price > ema200
- Sell signal: RSI > rsi_overbought OR current_price < ema200
- Take profit triggers when net_pnl_pct >= take_profit_net (using calc_pnl)
- Stop loss triggers when net_pnl_pct <= -stop_loss (using calc_pnl)
- TP/SL prices calculated as entry * (1 ± pct/100)
- ALL_STRATEGIES contains "rsi_ema"
</acceptance_criteria>

---

## Artifacts this phase produces

| File | Purpose |
|------|---------|
| `src/strategies/dca.py` | DCA strategy: accumulates on dips, sells at take_profit_net |
| `src/strategies/rsi_ema.py` | RSI+EMA strategy: oversold+EMA200 filter, TP/SL |
| `src/strategies/__init__.py` | Updated with dca and rsi_ema registrations |
