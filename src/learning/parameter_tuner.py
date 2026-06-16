import numpy as np
from datetime import datetime
from loguru import logger
import optuna
from src.learning.model_store import save_params, load_latest_params
from src.learning.anomaly_guard import AnomalyGuard
from src.database.session import SessionLocal
from src.database.models import Trade
from src.core.capital import calc_pnl

optuna.logging.set_verbosity(optuna.logging.WARNING)

TRADES_PER_OPTIMIZATION = 50
MIN_IMPROVEMENT_PCT = 10.0
WALK_FORWARD_TRAIN_RATIO = 0.8

PARAM_SPACES = {
    "grid": {
        "grid_step_pct": {"type": "float", "low": 0.5, "high": 3.0},
        "grid_count": {"type": "int", "low": 5, "high": 20},
    },
    "dca": {
        "price_deviation": {"type": "float", "low": 1.0, "high": 5.0},
        "take_profit_net": {"type": "float", "low": 0.5, "high": 4.0},
        "stop_loss": {"type": "float", "low": 3.0, "high": 15.0},
    },
    "rsi_ema": {
        "rsi_oversold": {"type": "int", "low": 20, "high": 45},
        "rsi_overbought": {"type": "int", "low": 55, "high": 80},
        "take_profit_net": {"type": "float", "low": 0.5, "high": 5.0},
        "stop_loss": {"type": "float", "low": 1.0, "high": 5.0},
    },
    "mtf": {
        "adx_threshold": {"type": "int", "low": 20, "high": 50},
        "take_profit_net": {"type": "float", "low": 1.0, "high": 6.0},
        "stop_loss": {"type": "float", "low": 1.0, "high": 4.0},
        "trailing_pct": {"type": "float", "low": 1.0, "high": 4.0},
    },
}


class ParameterTuner:
    def __init__(self, strategy_manager, anomaly_guard=None):
        self.strategy_manager = strategy_manager
        self.anomaly_guard = anomaly_guard or AnomalyGuard()
        self._last_optimization: dict[str, int] = {}

    def should_optimize(self, strategy_name: str) -> bool:
        db = SessionLocal()
        try:
            trade_count = db.query(Trade).filter(
                Trade.strategy == strategy_name,
                Trade.status == "CLOSED",
            ).count()
            last_count = self._last_optimization.get(strategy_name, 0)
            return trade_count - last_count >= TRADES_PER_OPTIMIZATION
        finally:
            db.close()

    def optimize(self, strategy_name: str) -> dict | None:
        if strategy_name not in PARAM_SPACES:
            logger.warning(f"ParameterTuner: нет пространства параметров для {strategy_name}")
            return None

        strategy = self.strategy_manager.strategies.get(strategy_name)
        if not strategy:
            return None

        current_params = strategy.get_params()
        trades = self._get_strategy_trades(strategy_name)
        if len(trades) < 30:
            logger.info(f"ParameterTuner: {strategy_name} имеет только {len(trades)} сделок, нужно 30+")
            return None

        split_idx = int(len(trades) * WALK_FORWARD_TRAIN_RATIO)
        train_trades = trades[:split_idx]
        test_trades = trades[split_idx:]

        study = optuna.create_study(direction="maximize")
        study.optimize(
            lambda trial: self._objective(trial, strategy_name, train_trades),
            n_trials=50,
            show_progress_bar=False,
        )

        best_params = study.best_params
        best_sharpe = study.best_value

        test_sharpe = self._evaluate_params(strategy_name, best_params, test_trades)
        current_sharpe = self._evaluate_params(strategy_name, current_params, test_trades)

        if current_sharpe == 0:
            improvement = best_sharpe * 100 if best_sharpe > 0 else 0
        else:
            improvement = ((best_sharpe - current_sharpe) / abs(current_sharpe) * 100)

        if improvement < MIN_IMPROVEMENT_PCT:
            logger.info(f"ParameterTuner: улучшение {strategy_name} {improvement:.1f}% < {MIN_IMPROVEMENT_PCT}%, пропуск")
            self._last_optimization[strategy_name] = self._get_trade_count(strategy_name)
            return None

        strategy.set_params(best_params)
        self._last_optimization[strategy_name] = self._get_trade_count(strategy_name)

        save_params(
            strategy=strategy_name,
            model_type="params",
            params_before=current_params,
            params_after=best_params,
            metrics={
                "sharpe_before": current_sharpe,
                "sharpe_after": best_sharpe,
                "trades_count": len(trades),
                "applied": True,
            },
        )

        logger.info(f"ParameterTuner: {strategy_name} обновлён, Sharpe {current_sharpe:.2f} -> {best_sharpe:.2f}")
        return best_params

    def _objective(self, trial, strategy_name: str, trades: list) -> float:
        space = PARAM_SPACES[strategy_name]
        params = {}
        for name, spec in space.items():
            if spec["type"] == "float":
                params[name] = trial.suggest_float(name, spec["low"], spec["high"])
            elif spec["type"] == "int":
                params[name] = trial.suggest_int(name, spec["low"], spec["high"])
        return self._evaluate_params(strategy_name, params, trades)

    def _evaluate_params(self, strategy_name: str, params: dict, trades: list) -> float:
        if not trades:
            return 0.0

        pnls = []
        for t in trades:
            pnl = calc_pnl(t.price, t.price * (1 + t.net_pnl_pct / 100), t.quantity)
            pnls.append(pnl["net_pnl"])

        if not pnls or all(p == 0 for p in pnls):
            return 0.0

        pnl_array = np.array(pnls)
        mean_pnl = np.mean(pnl_array)
        std_pnl = np.std(pnl_array) if np.std(pnl_array) > 0 else 1.0
        return mean_pnl / std_pnl

    def _get_strategy_trades(self, strategy_name: str) -> list:
        db = SessionLocal()
        try:
            return db.query(Trade).filter(
                Trade.strategy == strategy_name,
                Trade.status == "CLOSED",
            ).order_by(Trade.closed_at).all()
        finally:
            db.close()

    def _get_trade_count(self, strategy_name: str) -> int:
        db = SessionLocal()
        try:
            return db.query(Trade).filter(
                Trade.strategy == strategy_name,
                Trade.status == "CLOSED",
            ).count()
        finally:
            db.close()

    def get_status(self) -> dict:
        return {
            "last_optimization": self._last_optimization,
            "trades_per_optimization": TRADES_PER_OPTIMIZATION,
            "param_spaces": {k: list(v.keys()) for k, v in PARAM_SPACES.items()},
        }
