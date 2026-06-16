from datetime import datetime, timedelta
from loguru import logger
from src.core.constants import MAX_OPEN_POSITIONS, RESERVED_USDT
from src.core.capital import get_capital_info
from src.database.session import SessionLocal
from src.database.models import Trade


class RiskManager:
    DAILY_LOSS_LIMIT_PCT = 5.0
    COOLDOWN_MINUTES = 15
    MAX_DRAWDOWN_PCT = 8.0

    def __init__(self, config: dict = None):
        if config:
            risk_cfg = config.get("risk", {})
            self.DAILY_LOSS_LIMIT_PCT = risk_cfg.get("daily_loss_limit_pct", 5.0)
            self.COOLDOWN_MINUTES = risk_cfg.get("cooldown_minutes", 15)
        self._cooldown_until: dict[str, datetime] = {}

    def can_trade(self, symbol: str) -> tuple[bool, str]:
        open_count = self._count_open_positions()
        if open_count >= MAX_OPEN_POSITIONS:
            return False, f"Max positions reached ({open_count}/{MAX_OPEN_POSITIONS})"

        daily_pnl = self._get_daily_pnl()
        capital_info = get_capital_info()
        if capital_info:
            daily_limit = capital_info["starting_capital"] * self.DAILY_LOSS_LIMIT_PCT / 100
            if daily_pnl < -daily_limit:
                return False, f"Daily loss limit: {daily_pnl:.2f} USDT (limit: -{daily_limit:.2f})"

        if capital_info:
            available = capital_info["balance"] - RESERVED_USDT
            if available < 0:
                return False, f"Reserve buffer: balance {capital_info['balance']:.2f} < {RESERVED_USDT} USDT"

        now = datetime.utcnow()
        if symbol in self._cooldown_until:
            if now < self._cooldown_until[symbol]:
                remaining = int((self._cooldown_until[symbol] - now).total_seconds() // 60)
                return False, f"Cooldown: {remaining} min remaining for {symbol}"

        return True, "OK"

    def trigger_cooldown(self, symbol: str):
        self._cooldown_until[symbol] = datetime.utcnow() + timedelta(minutes=self.COOLDOWN_MINUTES)
        logger.info(f"RiskManager: cooldown {self.COOLDOWN_MINUTES}min started for {symbol}")

    def check_drawdown(self) -> bool:
        capital_info = get_capital_info()
        if not capital_info:
            return False
        if capital_info["drawdown_pct"] > self.MAX_DRAWDOWN_PCT:
            logger.warning(f"RiskManager: drawdown {capital_info['drawdown_pct']:.2f}% > {self.MAX_DRAWDOWN_PCT}% — STOP TRADING")
            return True
        return False

    def get_status(self) -> dict:
        capital_info = get_capital_info()
        open_count = self._count_open_positions()
        daily_pnl = self._get_daily_pnl()
        return {
            "open_positions": open_count,
            "max_positions": MAX_OPEN_POSITIONS,
            "daily_pnl": round(daily_pnl, 4),
            "daily_loss_limit": round(
                capital_info["starting_capital"] * self.DAILY_LOSS_LIMIT_PCT / 100, 4
            ) if capital_info else 0,
            "drawdown_pct": capital_info["drawdown_pct"] if capital_info else 0,
            "cooldowns": {
                sym: exp.isoformat()
                for sym, exp in self._cooldown_until.items()
                if exp > datetime.utcnow()
            },
        }

    def _count_open_positions(self) -> int:
        db = SessionLocal()
        try:
            return db.query(Trade).filter(Trade.status == "OPEN").count()
        finally:
            db.close()

    def _get_daily_pnl(self) -> float:
        db = SessionLocal()
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            result = db.query(Trade.net_pnl).filter(
                Trade.status == "CLOSED",
                Trade.closed_at >= today_start,
            ).all()
            return sum(r[0] for r in result) if result else 0.0
        finally:
            db.close()
