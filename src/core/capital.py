from datetime import datetime
from sqlalchemy import func
from src.database.session import SessionLocal
from src.database.models import BotSession, Trade
from src.core.constants import FEE_RATE


def init_capital(amount: float, mode: str = "testnet") -> BotSession:
    db = SessionLocal()
    try:
        session = BotSession(
            starting_capital=amount,
            started_at=datetime.utcnow(),
            mode=mode,
            total_trades=0,
            total_net_pnl=0.0,
            max_balance=amount,
            current_drawdown=0.0,
            status="active",
        )
        db.add(session)
        db.commit()
        return session
    finally:
        db.close()


def get_capital_info(binance_client=None) -> dict | None:
    db = SessionLocal()
    try:
        session = db.query(BotSession).order_by(-BotSession.id).first()
        if not session:
            return None

        # Get real balance from Binance
        real_balance = 0.0
        if binance_client:
            try:
                real_balance = binance_client.get_balance("USDT")
            except Exception:
                pass

        # PnL = real balance - starting capital
        net_pnl = real_balance - session.starting_capital

        # Calculate unrealized PnL from open trades
        open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
        unrealized_pnl = 0.0
        total_invested = 0.0
        
        for trade in open_trades:
            total_invested += trade.total_usdt
            if binance_client:
                try:
                    current_price = binance_client.get_price(trade.symbol)
                    if current_price > 0:
                        current_value = trade.quantity * current_price
                        unrealized_pnl += current_value - trade.total_usdt
                except Exception:
                    pass

        # Total fees
        total_fees = db.query(func.coalesce(func.sum(Trade.fee_total), 0.0)).scalar()

        # Calculate drawdown dynamically
        max_balance = max(session.max_balance, real_balance)
        drawdown_pct = 0.0
        if max_balance > 0:
            drawdown_pct = ((max_balance - real_balance) / max_balance) * 100

        return {
            "starting_capital": session.starting_capital,
            "real_balance": round(real_balance, 2),
            "net_pnl": round(net_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "current_balance": round(real_balance, 2),
            "total_with_open": round(real_balance + unrealized_pnl, 2),
            "total_fees": round(total_fees, 2),
            "open_positions": len(open_trades),
            "max_balance": max_balance,
            "drawdown_pct": round(drawdown_pct, 2),
            "roi_pct": round((net_pnl / session.starting_capital * 100) if session.starting_capital > 0 else 0, 2),
        }
    finally:
        db.close()


def update_drawdown_stats() -> None:
    db = SessionLocal()
    try:
        session = db.query(BotSession).order_by(-BotSession.id).first()
        if not session:
            return

        net_pnl = db.query(func.coalesce(func.sum(Trade.net_pnl), 0.0)).filter(
            Trade.status == "CLOSED"
        ).scalar()

        current_balance = session.starting_capital + net_pnl

        if current_balance > session.max_balance:
            session.max_balance = current_balance
        if session.max_balance > 0:
            session.current_drawdown = (session.max_balance - current_balance) / session.max_balance * 100
        db.commit()
    finally:
        db.close()


def calc_pnl(buy_price: float, sell_price: float, qty: float) -> dict:
    buy_total = buy_price * qty
    sell_total = sell_price * qty
    fee_buy = buy_total * FEE_RATE
    fee_sell = sell_total * FEE_RATE
    gross_pnl = sell_total - buy_total
    net_pnl = gross_pnl - fee_buy - fee_sell
    return {
        "gross_pnl": round(gross_pnl, 4),
        "fee_buy": round(fee_buy, 4),
        "fee_sell": round(fee_sell, 4),
        "fee_total": round(fee_buy + fee_sell, 4),
        "net_pnl": round(net_pnl, 4),
        "net_pnl_pct": round(net_pnl / buy_total * 100, 3) if buy_total > 0 else 0,
    }
