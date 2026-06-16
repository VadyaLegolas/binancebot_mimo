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

        tf_klines = self._fetch_multi_tf(symbol)

        tf_indicators = {}
        for tf in self.timeframes:
            if tf in tf_klines and len(tf_klines[tf]) >= 20:
                from src.indicators import calc_indicators
                tf_indicators[tf] = calc_indicators(tf_klines[tf])

        if len(tf_indicators) < len(self.timeframes):
            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="MTF: insufficient kline data")

        if symbol in self._positions:
            pos = self._positions[symbol]

            if self.trailing_stop and current_price > pos.highest_since_entry:
                pos.highest_since_entry = current_price
                pos.stop_price = current_price * (1 - self.trailing_pct / 100)

            pnl = calc_pnl(pos.entry_price, current_price, pos.quantity)

            if pnl["net_pnl_pct"] >= self.take_profit_net:
                self._positions.pop(symbol, None)
                logger.info(f"MTF {symbol}: TAKE PROFIT at {current_price}, net {pnl['net_pnl_pct']:.2f}%")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"MTF TP: {pnl['net_pnl_pct']:.2f}%",
                )

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

            rsi_15m = tf_indicators.get("15m", {}).get("rsi", 50)
            if rsi_15m < 40:
                self._positions.pop(symbol, None)
                logger.info(f"MTF {symbol}: MOMENTUM WEAK (RSI 15m={rsi_15m:.1f})")
                return TradeAction(
                    signal=Signal.SELL, symbol=symbol, quantity=pos.quantity,
                    reason=f"MTF momentum weak: RSI 15m={rsi_15m:.1f}",
                )

            return TradeAction(signal=Signal.HOLD, symbol=symbol, reason="MTF holding")

        adx_4h = tf_indicators.get("4h", {}).get("adx", 0)
        rsi_4h = tf_indicators.get("4h", {}).get("rsi", 50)
        rsi_1h = tf_indicators.get("1h", {}).get("rsi", 50)
        rsi_15m = tf_indicators.get("15m", {}).get("rsi", 50)

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
