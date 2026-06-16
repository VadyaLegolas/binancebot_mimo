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
    buys: list = field(default_factory=list)
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

        if symbol in self._positions and self._positions[symbol].orders_count > 0:
            pos = self._positions[symbol]

            if pos.avg_entry > 0:
                pnl = calc_pnl(pos.avg_entry, current_price, pos.total_quantity)
                if pnl["net_pnl_pct"] >= self.take_profit_net:
                    qty = pos.total_quantity
                    self._positions.pop(symbol, None)
                    logger.info(f"DCA {symbol}: TAKE PROFIT at {current_price}, net PnL {pnl['net_pnl_pct']:.2f}%")
                    return TradeAction(
                        signal=Signal.SELL, symbol=symbol, quantity=qty,
                        reason=f"DCA take profit: {pnl['net_pnl_pct']:.2f}%",
                    )

                if pnl["net_pnl_pct"] <= -self.stop_loss:
                    qty = pos.total_quantity
                    self._positions.pop(symbol, None)
                    logger.info(f"DCA {symbol}: STOP LOSS at {current_price}, net PnL {pnl['net_pnl_pct']:.2f}%")
                    return TradeAction(
                        signal=Signal.SELL, symbol=symbol, quantity=qty,
                        reason=f"DCA stop loss: {pnl['net_pnl_pct']:.2f}%",
                    )

            if pos.orders_count < pos.max_orders and pos.last_buy_price > 0:
                drop_pct = (pos.last_buy_price - current_price) / pos.last_buy_price * 100
                if drop_pct >= self.price_deviation:
                    return self._execute_buy(symbol, current_price)

            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="DCA holding")

        if rsi < 35:
            return self._execute_buy(symbol, current_price)

        return TradeAction(signal=Signal.HOLD, symbol=symbol, reason=f"DCA waiting (RSI={rsi:.1f})")

    def _execute_buy(self, symbol: str, current_price: float) -> TradeAction:
        if symbol not in self._positions:
            self._positions[symbol] = DCAPosition(symbol=symbol, max_orders=self.max_orders)

        pos = self._positions[symbol]
        if pos.orders_count >= pos.max_orders:
            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="DCA max orders reached")

        fee = self.amount_per_buy * FEE_RATE
        net_usdt = self.amount_per_buy - fee
        qty = net_usdt / current_price

        if self.amount_per_buy < MIN_TRADE_USDT:
            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="DCA below min trade")

        pos.buys.append({
            "price": current_price,
            "quantity": qty,
            "timestamp": datetime.utcnow().isoformat(),
            "cost_usdt": self.amount_per_buy,
        })
        pos.total_quantity += qty
        pos.total_cost += self.amount_per_buy
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
