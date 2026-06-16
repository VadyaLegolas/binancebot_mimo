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

        if symbol in self._positions:
            pos = self._positions[symbol]
            pnl = calc_pnl(pos.entry_price, current_price, pos.quantity)

            if pnl["net_pnl_pct"] >= self.take_profit_net:
                self._positions.pop(symbol, None)
                logger.info(f"RSI+EMA {symbol}: TAKE PROFIT at {current_price}, net {pnl['net_pnl_pct']:.2f}%")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"RSI+EMA TP: {pnl['net_pnl_pct']:.2f}%",
                )

            if pnl["net_pnl_pct"] <= -self.stop_loss:
                self._positions.pop(symbol, None)
                logger.info(f"RSI+EMA {symbol}: STOP LOSS at {current_price}, net {pnl['net_pnl_pct']:.2f}%")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"RSI+EMA SL: {pnl['net_pnl_pct']:.2f}%",
                )

            if rsi > self.rsi_overbought or current_price < ema200:
                self._positions.pop(symbol, None)
                logger.info(f"RSI+EMA {symbol}: SELL signal (RSI={rsi:.1f}, price vs EMA200)")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"RSI+EMA exit: RSI={rsi:.1f}",
                )

            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="RSI+EMA holding")

        if rsi < self.rsi_oversold and current_price > ema200:
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
