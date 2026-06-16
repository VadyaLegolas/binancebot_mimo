---
wave: 1
depends_on: []
files_modified:
  - requirements.txt
  - src/learning/__init__.py
  - src/learning/parameter_tuner.py
  - src/learning/anomaly_guard.py
  - src/learning/model_store.py
requirements_addressed:
  - LRN-01
  - LRN-04
autonomous: true
---

# Plan 1 — Parameter Tuner + Anomaly Guard + Model Store

<objective>
Implement the Optuna-based Parameter Tuner that optimizes strategy parameters every 50 closed trades using Walk-Forward Validation, the Anomaly Guard that detects degradation and triggers rollbacks, and the Model Store for persisting/loading optimization results. By end of this plan: parameter_tuner can run an Optuna study on historical trade data, anomaly_guard detects win rate drops and drawdown spikes, and model_store saves/loads parameter snapshots.
</objective>

---

## Task 1.1 — Add ML dependencies to requirements.txt

<read_first>
- requirements.txt (current dependencies)
</read_first>

<action>
1. Add to `requirements.txt`:
   ```
   optuna==4.9.0
   scikit-learn==1.8.0
   ```
2. Run `pip install optuna==4.9.0 scikit-learn==1.8.0`
</action>

<acceptance_criteria>
- requirements.txt contains optuna and scikit-learn
- `python -c "import optuna; import sklearn"` succeeds
</acceptance_criteria>

---

## Task 1.2 — Create Model Store

<read_first>
- src/database/models.py (ModelHistory model)
- src/database/session.py (SessionLocal)
- src/learning/__init__.py (currently empty)
</read_first>

<action>
1. Write `src/learning/model_store.py`:

```python
import json
from datetime import datetime
from loguru import logger
from src.database.session import SessionLocal
from src.database.models import ModelHistory


def save_params(strategy: str, model_type: str, params_before: dict,
                params_after: dict, metrics: dict) -> None:
    """Save parameter change to model_history table."""
    db = SessionLocal()
    try:
        record = ModelHistory(
            strategy=strategy,
            model_type=model_type,
            params_before=json.dumps(params_before),
            params_after=json.dumps(params_after),
            sharpe_before=metrics.get("sharpe_before"),
            sharpe_after=metrics.get("sharpe_after"),
            win_rate_before=metrics.get("win_rate_before"),
            win_rate_after=metrics.get("win_rate_after"),
            trades_count=metrics.get("trades_count"),
            applied=metrics.get("applied", True),
        )
        db.add(record)
        db.commit()
        logger.info(f"ModelStore: saved {model_type} params for {strategy}")
    finally:
        db.close()


def load_latest_params(strategy: str, model_type: str = "params") -> dict | None:
    """Load the most recent applied parameters for a strategy."""
    db = SessionLocal()
    try:
        record = db.query(ModelHistory).filter(
            ModelHistory.strategy == strategy,
            ModelHistory.model_type == model_type,
            ModelHistory.applied == True,
        ).order_by(-ModelHistory.created_at).first()
        if record and record.params_after:
            return json.loads(record.params_after)
        return None
    finally:
        db.close()


def get_param_history(strategy: str, model_type: str = "params", limit: int = 10) -> list:
    """Get recent parameter change history for a strategy."""
    db = SessionLocal()
    try:
        records = db.query(ModelHistory).filter(
            ModelHistory.strategy == strategy,
            ModelHistory.model_type == model_type,
        ).order_by(-ModelHistory.created_at).limit(limit).all()
        return [{
            "id": r.id,
            "params_before": json.loads(r.params_before) if r.params_before else None,
            "params_after": json.loads(r.params_after) if r.params_after else None,
            "sharpe_before": r.sharpe_before,
            "sharpe_after": r.sharpe_after,
            "win_rate_before": r.win_rate_before,
            "win_rate_after": r.win_rate_after,
            "applied": r.applied,
            "created_at": str(r.created_at),
        } for r in records]
    finally:
        db.close()
```
</action>

<acceptance_criteria>
- `from src.learning.model_store import save_params, load_latest_params, get_param_history` works
- `save_params("grid", "params", {}, {"grid_step_pct": 0.5}, {"sharpe_after": 1.2})` inserts a row
- `load_latest_params("grid")` returns the saved dict
- `get_param_history("grid")` returns list of records
</acceptance_criteria>

---

## Task 1.3 — Create Anomaly Guard

<read_first>
- src/core/constants.py (MAX_OPEN_POSITIONS, FEE_RATE)
- src/core/capital.py (get_capital_info)
- src/database/session.py (SessionLocal)
- src/database/models.py (Trade, Alert)
- binance_bot_spec_v2.md §6.4 (Anomaly Guard rules)
- src/telegram_bot/handlers.py (for send_notification reference)
</read_first>

<action>
1. Write `src/learning/anomaly_guard.py`:

```python
from datetime import datetime, timedelta
from loguru import logger
from src.database.session import SessionLocal
from src.database.models import Trade, Alert, ModelHistory
from src.core.capital import get_capital_info
import json


class AnomalyGuard:
    """Detects degradation and triggers rollbacks."""

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
        """Run all anomaly checks. Returns list of triggered anomalies."""
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
        """Win Rate < 40% over last 20 trades → rollback params."""
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
        """Drawdown > 8% → stop all trading."""
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
        """Fees > 50% of PnL → alert excessive trading."""
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
        """RL agent > 3 consecutive losses → shadow mode."""
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
        """Rollback to previous parameters for a strategy."""
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
            previous = records[1]

            current.applied = False
            db.commit()

            logger.info(f"AnomalyGuard: Rolled back {strategy} params from {current.id} to {previous.id}")
            return True
        finally:
            db.close()

    def save_anomaly_alert(self, anomaly: dict) -> None:
        """Save anomaly to alerts table."""
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
```
</action>

<acceptance_criteria>
- `from src.learning.anomaly_guard import AnomalyGuard` works
- `AnomalyGuard().check_all()` returns list of anomaly dicts
- `check_win_rate()` returns anomaly when WR < 40% over 20 trades
- `check_drawdown()` returns anomaly when drawdown > 8%
- `check_fee_ratio()` returns anomaly when fees > 50% of PnL
- `rollback_latest_params("grid")` marks current params as not applied
- All checks handle empty database gracefully
</acceptance_criteria>

---

## Task 1.4 — Create Parameter Tuner

<read_first>
- src/strategies/__init__.py (ALL_STRATEGIES)
- src/strategies/base.py (BaseStrategy get_params, set_params)
- src/learning/model_store.py (save_params, load_latest_params)
- src/learning/anomaly_guard.py (AnomalyGuard)
- src/database/session.py (SessionLocal)
- src/database/models.py (Trade)
- src/core/capital.py (calc_pnl)
- binance_bot_spec_v2.md §6.1 (Parameter Tuner spec)
- config.yaml (strategy params)
</read_first>

<action>
1. Write `src/learning/parameter_tuner.py`:

```python
import json
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

# Parameter search spaces per strategy
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
    """Optuna-based parameter optimization for strategies."""

    def __init__(self, strategy_manager):
        self.strategy_manager = strategy_manager
        self.anomaly_guard = AnomalyGuard()
        self._last_optimization: dict[str, int] = {}

    def should_optimize(self, strategy_name: str) -> bool:
        """Check if strategy has enough closed trades since last optimization."""
        db = SessionLocal()
        try:
            trade_count = db.query(Trade).filter(
                Trade.strategy == strategy_name,
                Trade.status == "CLOSED",
            ).count()

            last_count = self._last_optimization.get(strategy_name, 0)
            if trade_count - last_count >= TRADES_PER_OPTIMIZATION:
                return True
            return False
        finally:
            db.close()

    def optimize(self, strategy_name: str) -> dict | None:
        """Run Optuna optimization for a strategy. Returns new params or None."""
        if strategy_name not in PARAM_SPACES:
            logger.warning(f"ParameterTuner: no param space defined for {strategy_name}")
            return None

        strategy = self.strategy_manager.strategies.get(strategy_name)
        if not strategy:
            return None

        current_params = strategy.get_params()
        space = PARAM_SPACES[strategy_name]

        trades = self._get_strategy_trades(strategy_name)
        if len(trades) < 30:
            logger.info(f"ParameterTuner: {strategy_name} has only {len(trades)} trades, need 30+")
            return None

        # Walk-forward split
        split_idx = int(len(trades) * WALK_FORWARD_TRAIN_RATIO)
        train_trades = trades[split_idx:]
        test_trades = trades[:split_idx]

        study = optuna.create_study(direction="maximize")
        study.optimize(
            lambda trial: self._objective(trial, strategy_name, train_trades),
            n_trials=50,
            show_progress_bar=False,
        )

        best_params = study.best_params
        best_sharpe = study.best_value

        # Validate on test set
        test_sharpe = self._evaluate_params(strategy_name, best_params, test_trades)
        current_sharpe = self._evaluate_params(strategy_name, current_params, test_trades)

        improvement = ((best_sharpe - current_sharpe) / abs(current_sharpe) * 100
                       if current_sharpe != 0 else best_sharpe * 100)

        if improvement < MIN_IMPROVEMENT_PCT:
            logger.info(f"ParameterTuner: {strategy_name} improvement {improvement:.1f}% < {MIN_IMPROVEMENT_PCT}%, skipping")
            self._last_optimization[strategy_name] = self._get_trade_count(strategy_name)
            return None

        # Apply new params
        strategy.set_params(best_params)
        self._last_optimization[strategy_name] = self._get_trade_count(strategy_name)

        # Save to DB
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

        logger.info(f"ParameterTuner: {strategy_name} updated, Sharpe {current_sharpe:.2f} → {best_sharpe:.2f}")
        return best_params

    def _objective(self, trial, strategy_name: str, trades: list) -> float:
        """Optuna objective function: simulate strategy with trial params."""
        space = PARAM_SPACES[strategy_name]
        params = {}
        for name, spec in space.items():
            if spec["type"] == "float":
                params[name] = trial.suggest_float(name, spec["low"], spec["high"])
            elif spec["type"] == "int":
                params[name] = trial.suggest_int(name, spec["low"], spec["high"])

        return self._evaluate_params(strategy_name, params, trades)

    def _evaluate_params(self, strategy_name: str, params: dict, trades: list) -> float:
        """Evaluate parameter set on trades, return Sharpe ratio."""
        if not trades:
            return 0.0

        pnls = []
        for t in trades:
            pnl = calc_pnl(t.price, t.price * (1 + t.net_pnl_pct / 100), t.quantity)
            pnls.append(pnl["net_pnl"])

        if not pnls or all(p == 0 for p in pnls):
            return 0.0

        import numpy as np
        pnl_array = np.array(pnls)
        mean_pnl = np.mean(pnl_array)
        std_pnl = np.std(pnl_array) if np.std(pnl_array) > 0 else 1.0
        return mean_pnl / std_pnl

    def _get_strategy_trades(self, strategy_name: str) -> list:
        """Get closed trades for a strategy, ordered by time."""
        db = SessionLocal()
        try:
            trades = db.query(Trade).filter(
                Trade.strategy == strategy_name,
                Trade.status == "CLOSED",
            ).order_by(Trade.closed_at).all()
            return trades
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
```
</action>

<acceptance_criteria>
- `from src.learning.parameter_tuner import ParameterTuner` works
- `ParameterTuner(strategy_manager)` accepts StrategyManager
- `should_optimize("grid")` returns True when 50+ new trades since last optimization
- `optimize("grid")` runs Optuna study and returns new params or None
- Walk-forward: trains on 80%, validates on 20%
- Skip if improvement < 10%
- Results saved to model_history via save_params
- All 4 strategies have defined param spaces
</acceptance_criteria>

---

## Artifacts this plan produces

| File | Purpose |
|------|---------|
| `src/learning/model_store.py` | Save/load parameter snapshots to model_history |
| `src/learning/anomaly_guard.py` | Detect degradation: win rate, drawdown, fees, RL losses |
| `src/learning/parameter_tuner.py` | Optuna optimization with Walk-Forward Validation |
