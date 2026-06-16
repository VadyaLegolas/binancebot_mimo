from datetime import datetime
from loguru import logger
from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.strategies.auto_selector import AutoSelector
from src.core.risk_manager import RiskManager
from src.core.capital import calc_pnl
from src.core.constants import FEE_RATE, CORE_PAIRS
from src.database.session import SessionLocal
from src.database.models import Trade
import os
import requests


def send_telegram(message: str):
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if token and chat_id:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
    except Exception:
        pass


class StrategyManager:
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
        for symbol in self._pairs:
            try:
                self.tick(symbol)
            except Exception as e:
                logger.error(f"Tick failed for {symbol}: {e}")

    def tick(self, symbol: str):
        if self.risk_manager.check_drawdown():
            logger.debug(f"Tick skipped {symbol}: drawdown > 8%")
            return

        can_trade, reason = self.risk_manager.can_trade(symbol)
        if not can_trade:
            logger.debug(f"Risk blocked {symbol}: {reason}")
            return

        if self.auto_mode:
            strategy_name = self.auto_selector.select(symbol)
            strategy = self.strategies.get(strategy_name)
        else:
            strategy = self.strategies.get(self.active_name)

        if not strategy:
            logger.debug(f"No strategy for {symbol}")
            return

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
        open_positions = self._get_open_positions(symbol)
        action = strategy.analyze(symbol, klines, current_price, open_positions)

        if action.signal == Signal.BUY:
            self._execute_buy(action, symbol, strategy.name)
        elif action.signal == Signal.SELL:
            self._execute_sell(action, symbol, strategy.name)

    def _execute_buy(self, action: TradeAction, symbol: str, strategy_name: str):
        try:
            if action.quote_qty:
                order = self.binance.place_market_buy(symbol, action.quote_qty)
            elif action.price and action.quantity:
                order = self.binance.place_limit_buy(symbol, action.price, action.quantity)
            else:
                logger.warning(f"Buy action for {symbol} has no qty/quote_qty")
                return

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
                send_telegram(f"🟢 ПОКУПКА {symbol}\nКоличество: {qty:.6f}\nЦена: ${price:,.2f}\nСумма: ${total_usdt:.2f}\nСтратегия: {strategy_name}")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Execute buy failed for {symbol}: {e}")

    def _execute_sell(self, action: TradeAction, symbol: str, strategy_name: str):
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

                    open_trade.status = "CLOSED"
                    open_trade.closed_at = datetime.utcnow()
                    open_trade.fee_sell = qty * sell_price * FEE_RATE
                    open_trade.fee_total = open_trade.fee_buy + open_trade.fee_sell
                    open_trade.gross_pnl = pnl["gross_pnl"]
                    open_trade.net_pnl = pnl["net_pnl"]
                    open_trade.net_pnl_pct = pnl["net_pnl_pct"]

                    if pnl["net_pnl_pct"] < 0:
                        self.risk_manager.trigger_cooldown(symbol)

                    db.commit()
                    logger.info(
                        f"SELL {symbol}: {qty:.6f} @ {sell_price:.2f} | "
                        f"net PnL: {pnl['net_pnl']:.4f} ({pnl['net_pnl_pct']:.2f}%)"
                    )
                    emoji = "🟢" if pnl['net_pnl'] >= 0 else "🔴"
                    send_telegram(f"{emoji} ПРОДАЖА {symbol}\nКоличество: {qty:.6f}\nЦена: ${sell_price:,.2f}\nPnL: ${pnl['net_pnl']:.2f} ({pnl['net_pnl_pct']:.2f}%)\nСтратегия: {strategy_name}")
                else:
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
