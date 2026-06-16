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


def get_capital_info() -> dict | None:
    db = SessionLocal()
    try:
        session = db.query(BotSession).order_by(-BotSession.id).first()
        if not session:
            return None

        net_pnl = db.query(func.coalesce(func.sum(Trade.net_pnl), 0.0)).filter(
            Trade.status == "CLOSED"
        ).scalar()

        # Calculate unrealized PnL from open trades
        open_trades = db.query(Trade).filter(Trade.status == "OPEN").all()
        unrealized_pnl = 0.0
        for trade in open_trades:
            # Use gross_pnl if available, otherwise use entry price vs current
            if trade.gross_pnl != 0:
                unrealized_pnl += trade.gross_pnl
            elif trade.total_usdt > 0:
                # Estimate: trade amount minus current value
                unrealized_pnl += 0  # Can't calculate without current price

        current_balance = session.starting_capital + net_pnl

        return {
            "starting_capital": session.starting_capital,
            "net_pnl": net_pnl,
            "unrealized_pnl": unrealized_pnl,
            "current_balance": current_balance,
            "total_with_open": current_balance + unrealized_pnl,
            "max_balance": session.max_balance,
            "drawdown_pct": session.current_drawdown,
            "roi_pct": (net_pnl / session.starting_capital * 100) if session.starting_capital > 0 else 0,
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
