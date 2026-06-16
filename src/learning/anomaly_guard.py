from datetime import datetime, timedelta
from loguru import logger
from src.database.session import SessionLocal
from src.database.models import Trade, Alert, ModelHistory
from src.core.capital import get_capital_info
import json


class AnomalyGuard:
    WIN_RATE_THRESHOLD = 40.0
    MIN_TRADES_FOR_CHECK = 20
    DRAWDOWN_THRESHOLD = 8.0
    SHARPE_THRESHOLD = 0.5
    FEE_RATIO_THRESHOLD = 0.5
    CONSECUTIVE_LOSSES_THRESHOLD = 3

    def __init__(self, config: dict = None):
        if config:
            guard_cfg = config.get("anomaly_guard", {})
            self.WIN_RATE_THRESHOLD = guard_cfg.get("win_rate_threshold", 40.0)
            self.DRAWDOWN_THRESHOLD = guard_cfg.get("drawdown_threshold", 8.0)

    def check_all(self) -> list[dict]:
        anomalies = []
        wr = self.check_win_rate()
        if wr:
            anomalies.append(wr)
        dd = self.check_drawdown()
        if dd:
            anomalies.append(dd)
        fee = self.check_fee_ratio()
        if fee:
            anomalies.append(fee)
        return anomalies

    def check_win_rate(self) -> dict | None:
        db = SessionLocal()
        try:
            recent = db.query(Trade).filter(
                Trade.status == "CLOSED",
            ).order_by(-Trade.closed_at).limit(self.MIN_TRADES_FOR_CHECK).all()

            if len(recent) < self.MIN_TRADES_FOR_CHECK:
                return None

            wins = sum(1 for t in recent if t.net_pnl > 0)
            win_rate = wins / len(recent) * 100

            if win_rate < self.WIN_RATE_THRESHOLD:
                logger.warning(f"AnomalyGuard: Win Rate {win_rate:.1f}% < {self.WIN_RATE_THRESHOLD}%")
                return {
                    "type": "low_win_rate",
                    "message": f"Win Rate {win_rate:.1f}% over last {len(recent)} trades",
                    "action": "rollback",
                    "win_rate": win_rate,
                }
            return None
        finally:
            db.close()

    def check_drawdown(self) -> dict | None:
        capital_info = get_capital_info()
        if not capital_info:
            return None
        if capital_info["drawdown_pct"] > self.DRAWDOWN_THRESHOLD:
            logger.warning(f"AnomalyGuard: Drawdown {capital_info['drawdown_pct']:.2f}% > {self.DRAWDOWN_THRESHOLD}%")
            return {
                "type": "high_drawdown",
                "message": f"Drawdown {capital_info['drawdown_pct']:.2f}% exceeds {self.DRAWDOWN_THRESHOLD}%",
                "action": "stop_trading",
                "drawdown_pct": capital_info["drawdown_pct"],
            }
        return None

    def check_fee_ratio(self) -> dict | None:
        db = SessionLocal()
        try:
            recent = db.query(Trade).filter(
                Trade.status == "CLOSED",
            ).order_by(-Trade.closed_at).limit(50).all()

            if not recent:
                return None

            total_pnl = sum(t.net_pnl for t in recent)
            total_fees = sum(t.fee_total for t in recent)

            if total_pnl > 0 and total_fees / total_pnl > self.FEE_RATIO_THRESHOLD:
                logger.warning(f"AnomalyGuard: Fee ratio {total_fees/total_pnl*100:.1f}% > {self.FEE_RATIO_THRESHOLD*100}%")
                return {
                    "type": "high_fees",
                    "message": f"Fees are {total_fees/total_pnl*100:.1f}% of PnL",
                    "action": "alert",
                    "fee_ratio": total_fees / total_pnl,
                }
            return None
        finally:
            db.close()

    def check_rl_consecutive_losses(self) -> dict | None:
        db = SessionLocal()
        try:
            recent = db.query(Trade).filter(
                Trade.status == "CLOSED",
                Trade.strategy == "rl_agent",
            ).order_by(-Trade.closed_at).limit(10).all()

            consecutive = 0
            for t in recent:
                if t.net_pnl < 0:
                    consecutive += 1
                else:
                    break

            if consecutive > self.CONSECUTIVE_LOSSES_THRESHOLD:
                logger.warning(f"AnomalyGuard: RL agent {consecutive} consecutive losses")
                return {
                    "type": "rl_consecutive_losses",
                    "message": f"RL agent {consecutive} consecutive losses",
                    "action": "shadow_mode",
                    "consecutive_losses": consecutive,
                }
            return None
        finally:
            db.close()

    def rollback_latest_params(self, strategy: str) -> bool:
        db = SessionLocal()
        try:
            records = db.query(ModelHistory).filter(
                ModelHistory.strategy == strategy,
                ModelHistory.model_type == "params",
                ModelHistory.applied == True,
            ).order_by(-ModelHistory.created_at).limit(2).all()

            if len(records) < 2:
                logger.warning(f"AnomalyGuard: No previous params to rollback for {strategy}")
                return False

            current = records[0]
            current.applied = False
            db.commit()

            logger.info(f"AnomalyGuard: Rolled back {strategy} params from {current.id}")
            return True
        finally:
            db.close()

    def save_anomaly_alert(self, anomaly: dict) -> None:
        db = SessionLocal()
        try:
            alert = Alert(
                type="anomaly",
                message=f"[{anomaly['type']}] {anomaly['message']}",
                sent=False,
                created_at=datetime.utcnow(),
            )
            db.add(alert)
            db.commit()
        finally:
            db.close()
