---
wave: 3
depends_on:
  - plan-2-dca-rsi-ema.md
files_modified:
  - src/strategies/mtf.py
  - src/strategies/auto_selector.py
  - src/strategies/__init__.py
requirements_addressed:
  - STRAT-04
  - STRAT-05
autonomous: true
---

# Plan 3 — MTF Momentum + AutoSelector

<objective>
Implement Multi-Timeframe Momentum strategy and the AutoSelector that routes to the best strategy based on market conditions (ADX, RSI). MTF requires fetching 3 kline intervals per tick and checking trailing stop state. AutoSelector uses ADX thresholds from the spec decision matrix.
</objective>

---

## Task 3.1 — Create MTF Momentum strategy

<read_first>
- src/strategies/base.py (BaseStrategy, Signal, TradeAction)
- src/core/binance_client.py (place_market_buy, place_market_sell, get_price)
- src/core/capital.py (calc_pnl)
- src/core/constants.py (FEE_RATE, MIN_TRADE_USDT)
- src/indicators/__init__.py (calc_indicators)
- binance_bot_spec_v2.md §6.4 (MTF Momentum spec)
- 02-RESEARCH.md "Multi-Timeframe Momentum" section (algorithm, TrailingStopState, fetch_multi_tf_klines)
- config.yaml (strategies.mtf section)
</read_first>

<action>
1. Write `src/strategies/mtf.py`:

```python
from dataclasses import dataclass
from loguru import logger
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.core.capital import calc_pnl
from src.core.constants import FEE_RATE, MIN_TRADE_USDT


@dataclass
class MTFPosition:
    symbol: str
    entry_price: float
    quantity: float
    cost_usdt: float
    highest_since_entry: float
    trailing_pct: float
    stop_price: float


class MTFMomentumStrategy(BaseStrategy):
    name = "mtf"

    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        cfg = config.get("strategies", {}).get("mtf", {})
        self.timeframes = cfg.get("timeframes", ["4h", "1h", "15m"])
        self.position_size = cfg.get("position_size", 15)
        self.take_profit_net = cfg.get("take_profit_net", 3.5)
        self.stop_loss = cfg.get("stop_loss", 2.0)
        self.trailing_stop = cfg.get("trailing_stop", True)
        self.trailing_pct = cfg.get("trailing_pct", 2.0)
        self.adx_threshold = cfg.get("adx_threshold", 35)
        self._positions: dict[str, MTFPosition] = {}

    def get_params(self) -> dict:
        return {
            "timeframes": self.timeframes,
            "position_size": self.position_size,
            "take_profit_net": self.take_profit_net,
            "stop_loss": self.stop_loss,
            "trailing_stop": self.trailing_stop,
            "trailing_pct": self.trailing_pct,
            "adx_threshold": self.adx_threshold,
        }

    def set_params(self, params: dict) -> None:
        for key in ("position_size", "take_profit_net", "stop_loss",
                     "trailing_stop", "trailing_pct", "adx_threshold"):
            if key in params:
                setattr(self, key, params[key])

    def analyze(self, symbol: str, klines: list[dict], current_price: float,
                open_positions: list) -> TradeAction:

        # Fetch multi-timeframe klines
        tf_klines = self._fetch_multi_tf(symbol)

        # Calculate indicators per timeframe
        tf_indicators = {}
        for tf in self.timeframes:
            if tf in tf_klines and len(tf_klines[tf]) >= 20:
                from src.indicators import calc_indicators
                tf_indicators[tf] = calc_indicators(tf_klines[tf])

        if len(tf_indicators) < len(self.timeframes):
            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="MTF: insufficient kline data")

        # Check existing position
        if symbol in self._positions:
            pos = self._positions[symbol]

            # Update trailing stop
            if self.trailing_stop and current_price > pos.highest_since_entry:
                pos.highest_since_entry = current_price
                pos.stop_price = current_price * (1 - self.trailing_pct / 100)

            pnl = calc_pnl(pos.entry_price, current_price, pos.quantity)

            # Take profit (net of fees)
            if pnl["net_pnl_pct"] >= self.take_profit_net:
                self._positions.pop(symbol, None)
                logger.info(f"MTF {symbol}: TAKE PROFIT at {current_price}, net {pnl['net_pnl_pct']:.2f}%")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"MTF TP: {pnl['net_pnl_pct']:.2f}%",
                )

            # Stop loss — either fixed or trailing
            if self.trailing_stop:
                if current_price <= pos.stop_price:
                    self._positions.pop(symbol, None)
                    logger.info(f"MTF {symbol}: TRAILING STOP at {current_price} (stop={pos.stop_price:.2f})")
                    return TradeAction(
                        signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                        reason=f"MTF trailing stop: {pos.stop_price:.2f}",
                    )
            else:
                if pnl["net_pnl_pct"] <= -self.stop_loss:
                    self._positions.pop(symbol, None)
                    logger.info(f"MTF {symbol}: STOP LOSS at {current_price}, net {pnl['net_pnl_pct']:.2f}%")
                    return TradeAction(
                        signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                        reason=f"MTF SL: {pnl['net_pnl_pct']:.2f}%",
                    )

            # Sell on momentum weakness (15m RSI < 40)
            rsi_15m = tf_indicators.get("15m", {}).get("rsi", 50)
            if rsi_15m < 40:
                self._positions.pop(symbol, None)
                logger.info(f"MTF {symbol}: MOMENTUM WEAK (RSI 15m={rsi_15m:.1f})")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"MTF momentum weak: RSI 15m={rsi_15m:.1f}",
                )

            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="MTF holding")

        # No position — check for entry signal
        adx_4h = tf_indicators.get("4h", {}).get("adx", 0)
        rsi_4h = tf_indicators.get("4h", {}).get("rsi", 50)
        rsi_1h = tf_indicators.get("1h", {}).get("rsi", 50)
        rsi_15m = tf_indicators.get("15m", {}).get("rsi", 50)

        # All 3 timeframes must agree: ADX > threshold, all RSI > 50
        if (adx_4h > self.adx_threshold and
                rsi_4h > 50 and rsi_1h > 50 and rsi_15m > 50):

            if self.position_size < MIN_TRADE_USDT:
                return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="MTF below min trade")

            fee = self.position_size * FEE_RATE
            net_usdt = self.position_size - fee
            qty = net_usdt / current_price

            self._positions[symbol] = MTFPosition(
                symbol=symbol, entry_price=current_price, quantity=qty,
                cost_usdt=self.position_size,
                highest_since_entry=current_price,
                trailing_pct=self.trailing_pct,
                stop_price=current_price * (1 - self.trailing_pct / 100),
            )

            logger.info(f"MTF {symbol}: BUY at {current_price}, ADX={adx_4h:.1f}, RSI 4h={rsi_4h:.1f} 1h={rsi_1h:.1f} 15m={rsi_15m:.1f}")
            return TradeAction(
                signal=Signal.BUY, symbol=symbol, quote_qty=self.position_size,
                reason=f"MTF entry: ADX={adx_4h:.1f}",
            )

        return TradeAction(
            signal=Signal.HOLD, symbol=symbol,
            reason=f"MTF waiting (ADX={adx_4h:.1f}, RSI: 4h={rsi_4h:.1f} 1h={rsi_1h:.1f} 15m={rsi_15m:.1f})",
        )

    def _fetch_multi_tf(self, symbol: str) -> dict:
        """Fetch klines for all configured timeframes."""
        klines = {}
        for tf in self.timeframes:
            try:
                raw = self.binance.client.get_klines(
                    symbol=f"{symbol}USDT",
                    interval=tf,
                    limit=250,
                )
                klines[tf] = [{
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                } for k in raw]
            except Exception as e:
                logger.error(f"MTF: failed to fetch {tf} klines for {symbol}: {e}")
                klines[tf] = []
        return klines

    def get_position(self, symbol: str) -> MTFPosition | None:
        return self._positions.get(symbol)
```

2. Update `src/strategies/__init__.py`:

```python
from src.strategies.base import BaseStrategy, Signal, TradeAction
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
</action>

<acceptance_criteria>
- `from src.strategies.mtf import MTFMomentumStrategy` works
- MTFMomentumStrategy inherits BaseStrategy
- `MTFMomentumStrategy.name == "mtf"`
- get_params() returns dict with timeframes, position_size, take_profit_net, stop_loss, trailing_stop, trailing_pct, adx_threshold
- Fetches klines for 3 timeframes: 4h, 1h, 15m
- Buy requires: ADX(4h) > adx_threshold AND RSI(4h) > 50 AND RSI(1h) > 50 AND RSI(15m) > 50
- Sell on: trailing stop hit, momentum weakness (15m RSI < 40), take profit, or stop loss
- Trailing stop updates highest_since_entry and recalculates stop_price on each tick
- ALL_STRATEGIES contains "mtf"
</acceptance_criteria>

---

## Task 3.2 — Create AutoSelector

<read_first>
- src/strategies/__init__.py (ALL_STRATEGIES)
- src/indicators/__init__.py (calc_indicators)
- src/core/binance_client.py (get_price, client.get_klines)
- binance_bot_spec_v2.md §6.5 (AutoSelector spec)
- 02-RESEARCH.md "AutoSelector Logic" section (decision matrix)
- config.yaml (auto_selector section)
</read_first>

<action>
1. Write `src/strategies/auto_selector.py`:

```python
from loguru import logger
from src.indicators import calc_indicators


class AutoSelector:
    """Selects strategy based on market conditions (ADX, RSI)."""

    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        self.enabled = config.get("auto_selector", {}).get("enabled", True)
        self._current_strategy: str | None = None

    def select(self, symbol: str) -> str:
        """Determine best strategy for current market conditions.
        
        Decision matrix from spec:
        - ADX < 20: Grid (range-bound)
        - 20 <= ADX < 35, RSI < 35: DCA (downtrend, accumulate)
        - 20 <= ADX < 35, RSI >= 35: RSI+EMA (trend with corrections)
        - ADX >= 35: MTF Momentum (strong trend)
        """
        if not self.enabled:
            return self._current_strategy or "grid"

        try:
            indicators = self._get_market_indicators(symbol)
        except Exception as e:
            logger.error(f"AutoSelector: failed to get indicators for {symbol}: {e}")
            return self._current_strategy or "grid"

        adx = indicators["adx"]
        rsi = indicators["rsi"]

        if adx < 20:
            strategy = "grid"
        elif adx < 35:
            if rsi < 35:
                strategy = "dca"
            else:
                strategy = "rsi_ema"
        else:  # adx >= 35
            strategy = "mtf"

        if strategy != self._current_strategy:
            logger.info(f"AutoSelector {symbol}: {self._current_strategy} -> {strategy} (ADX={adx:.1f}, RSI={rsi:.1f})")
            self._current_strategy = strategy

        return strategy

    def _get_market_indicators(self, symbol: str) -> dict:
        """Fetch 1h klines and calculate indicators."""
        raw = self.binance.client.get_klines(
            symbol=f"{symbol}USDT",
            interval="1h",
            limit=250,
        )
        klines = [{
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        } for k in raw]
        return calc_indicators(klines)

    def get_current_strategy(self) -> str | None:
        return self._current_strategy
```
</action>

<acceptance_criteria>
- `from src.strategies.auto_selector import AutoSelector` works
- AutoSelector.select(symbol) returns one of: "grid", "dca", "rsi_ema", "mtf"
- Returns "grid" when ADX < 20
- Returns "dca" when 20 <= ADX < 35 AND RSI < 35
- Returns "rsi_ema" when 20 <= ADX < 35 AND RSI >= 35
- Returns "mtf" when ADX >= 35
- Logs strategy switches
- When disabled, returns last known strategy or "grid"
- Falls back to "grid" on error
</acceptance_criteria>

---

## Artifacts this phase produces

| File | Purpose |
|------|---------|
| `src/strategies/mtf.py` | Multi-Timeframe Momentum with trailing stop and 3-timeframe signal alignment |
| `src/strategies/auto_selector.py` | ADX/RSI-based strategy routing per spec decision matrix |
| `src/strategies/__init__.py` | Updated with mtf registration (4 strategies total) |
