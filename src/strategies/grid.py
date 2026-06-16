from dataclasses import dataclass
from loguru import logger
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.core.constants import FEE_RATE, MIN_TRADE_USDT


@dataclass
class GridLevel:
    price: float
    side: str
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
        self._grids: dict[str, list[GridLevel]] = {}

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

        if symbol not in self._grids or not self._grids[symbol]:
            return self._create_grid(symbol, current_price)

        grid = self._grids[symbol]
        for level in grid:
            if level.filled or level.order_id is None:
                continue
            open_orders = self.binance.get_open_orders(symbol)
            open_ids = {o["orderId"] for o in open_orders}
            if level.order_id not in open_ids:
                level.filled = True
                if level.side == "BUY":
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
        from src.indicators import calc_indicators

        half_range = current_price * self.grid_step_pct / 100 * self.grid_count / 2
        lower = current_price - half_range
        upper = current_price + half_range

        step_price = (upper - lower) / self.grid_count
        per_level_usdt = self.investment_usdt / self.grid_count

        grid = []
        levels_placed = 0

        for i in range(self.grid_count):
            level_price = lower + step_price * (i + 1)
            qty = per_level_usdt / level_price
            if per_level_usdt < MIN_TRADE_USDT:
                continue

            try:
                if level_price >= current_price:
                    order = self.binance.place_limit_sell(symbol, level_price, qty)
                    grid.append(GridLevel(price=level_price, side="SELL", order_id=order["orderId"], quantity=qty))
                else:
                    order = self.binance.place_limit_buy(symbol, level_price, qty)
                    grid.append(GridLevel(price=level_price, side="BUY", order_id=order["orderId"], quantity=qty))
                levels_placed += 1
            except Exception as e:
                logger.error(f"Grid: failed to place order at {level_price}: {e}")

        self._grids[symbol] = grid
        logger.info(f"Grid {symbol}: created {levels_placed} levels, range {lower:.2f}-{upper:.2f}")
        return TradeAction(signal=Signal.HOLD, symbol=symbol, reason=f"Grid created: {levels_placed} levels")

    def _calc_grid_qty(self, price: float) -> float:
        per_level_usdt = self.investment_usdt / self.grid_count
        return per_level_usdt / price

    def cancel_grid(self, symbol: str):
        if symbol in self._grids:
            for level in self._grids[symbol]:
                if level.order_id and not level.filled:
                    try:
                        self.binance.cancel_order(symbol, level.order_id)
                    except Exception:
                        pass
            self._grids.pop(symbol, None)
            logger.info(f"Grid {symbol}: cancelled all orders")
