from loguru import logger
from src.core.constants import CORE_PAIRS, EXTENDED_PAIRS, DOGE_PAIRS
from src.database.session import SessionLocal
from src.database.models import Trade


class PairManager:
    EXTENDED_AFTER = 50
    DOGE_AFTER = 100

    def __init__(self, config: dict):
        pairs_cfg = config.get("trading_pairs", {})
        self._custom_pairs = pairs_cfg.get("custom", [])

    def get_active_pairs(self) -> list[str]:
        total_trades = self._count_closed_trades()
        winning_trades = self._count_winning_trades()

        pairs = list(CORE_PAIRS)

        if total_trades >= self.EXTENDED_AFTER:
            pairs.extend(EXTENDED_PAIRS)

        if winning_trades >= self.DOGE_AFTER:
            pairs.extend(DOGE_PAIRS)

        pairs.extend(self._custom_pairs)
        return list(dict.fromkeys(pairs))

    def can_trade_doge(self) -> bool:
        return self._count_winning_trades() >= self.DOGE_AFTER

    def _count_closed_trades(self) -> int:
        db = SessionLocal()
        try:
            return db.query(Trade).filter(Trade.status == "CLOSED").count()
        finally:
            db.close()

    def _count_winning_trades(self) -> int:
        db = SessionLocal()
        try:
            return db.query(Trade).filter(
                Trade.status == "CLOSED",
                Trade.net_pnl > 0,
            ).count()
        finally:
            db.close()

    def get_status(self) -> dict:
        return {
            "active_pairs": self.get_active_pairs(),
            "total_trades": self._count_closed_trades(),
            "winning_trades": self._count_winning_trades(),
            "extended_unlocked": self._count_closed_trades() >= self.EXTENDED_AFTER,
            "doge_unlocked": self._count_winning_trades() >= self.DOGE_AFTER,
        }
