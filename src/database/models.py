from sqlalchemy import String, Float, Integer, DateTime, Boolean, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class BotSession(Base):
    __tablename__ = "bot_session"

    id: Mapped[int] = mapped_column(primary_key=True)
    starting_capital: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    max_balance: Mapped[float] = mapped_column(Float, default=0.0)
    current_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(10), default="active")
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime, onupdate=func.now())


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    strategy: Mapped[str] = mapped_column(String(20), nullable=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    total_usdt: Mapped[float] = mapped_column(Float, nullable=False)
    fee_rate: Mapped[float] = mapped_column(Float, default=0.001)
    fee_buy: Mapped[float] = mapped_column(Float, default=0.0)
    fee_sell: Mapped[float] = mapped_column(Float, default=0.0)
    fee_total: Mapped[float] = mapped_column(Float, default=0.0)
    gross_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    opened_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    closed_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class ModelHistory(Base):
    __tablename__ = "model_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False)
    params_before: Mapped[str] = mapped_column(Text, nullable=True)
    params_after: Mapped[str] = mapped_column(Text, nullable=True)
    sharpe_before: Mapped[float] = mapped_column(Float, nullable=True)
    sharpe_after: Mapped[float] = mapped_column(Float, nullable=True)
    win_rate_before: Mapped[float] = mapped_column(Float, nullable=True)
    win_rate_after: Mapped[float] = mapped_column(Float, nullable=True)
    trades_count: Mapped[int] = mapped_column(Integer, nullable=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
