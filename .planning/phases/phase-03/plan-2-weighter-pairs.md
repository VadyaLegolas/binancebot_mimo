---
wave: 2
depends_on:
  - plan-1-tuner-anomaly.md
files_modified:
  - src/learning/strategy_weighter.py
  - src/learning/__init__.py
  - src/strategies/auto_selector.py
  - src/core/constants.py
  - config.yaml
requirements_addressed:
  - LRN-02
  - PAIR-02
  - PAIR-03
autonomous: true
---

# Plan 2 — Strategy Weighter + Pair Expansion

<objective>
Implement the SGD-based Strategy Weighter that adapts strategy weights every 4 hours based on recent performance, and expand trading pairs with rules for BNB/XRP/ADA (after 50 trades) and DOGE (Grid only, after 100+ wins). By end of this plan: strategy_weighter learns from market conditions and adjusts weights, AutoSelector uses learned weights, and pair expansion logic works.
</objective>

---

## Task 2.1 — Create Strategy Weighter

<read_first>
- src/strategies/__init__.py (ALL_STRATEGIES)
- src/indicators/__init__.py (calc_indicators)
- src/database/session.py (SessionLocal)
- src/database/models.py (Trade)
- binance_bot_spec_v2.md §6.2 (Strategy Weighter spec)
- config.yaml (auto_selector section)
</read_first>

<action>
1. Write `src/learning/strategy_weighter.py`:

```python
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
from sklearn.linear_model import SGDClassifier
from src.indicators import calc_indicators
from src.database.session import SessionLocal
from src.database.models import Trade
import pickle
import os

WEIGHT_UPDATE_HOURS = 4
MIN_SAMPLES = 20
STRATEGY_NAMES = ["grid", "dca", "rsi_ema", "mtf"]
MODEL_PATH = "data/strategy_weighter.pkl"


class StrategyWeighter:
    """SGD online learning for strategy weights based on market conditions."""

    FEATURE_NAMES = [
        "adx", "rsi", "atr_pct", "volume_ratio",
        "hour_of_day", "day_of_week", "last_pnl",
    ]

    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        self.enabled = config.get("auto_selector", {}).get("enabled", True)
        self._model: SGDClassifier | None = None
        self._weights: dict[str, float] = {s: 1.0 / len(STRATEGY_NAMES) for s in STRATEGY_NAMES}
        self._last_update: datetime | None = None
        self._load_model()

    def _load_model(self):
        """Load saved model if exists."""
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "rb") as f:
                    data = pickle.load(f)
                    self._model = data.get("model")
                    self._weights = data.get("weights", self._weights)
                    self._last_update = data.get("last_update")
                logger.info("StrategyWeighter: loaded model from disk")
            except Exception as e:
                logger.error(f"StrategyWeighter: failed to load model: {e}")

    def _save_model(self):
        """Save model to disk."""
        os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
        try:
            with open(MODEL_PATH, "wb") as f:
                pickle.dump({
                    "model": self._model,
                    "weights": self._weights,
                    "last_update": self._last_update,
                }, f)
        except Exception as e:
            logger.error(f"StrategyWeighter: failed to save model: {e}")

    def should_update(self) -> bool:
        """Check if 4+ hours since last update."""
        if not self._last_update:
            return True
        elapsed = datetime.utcnow() - self._last_update
        return elapsed >= timedelta(hours=WEIGHT_UPDATE_HOURS)

    def update(self) -> dict[str, float]:
        """Retrain SGD classifier and update weights. Returns new weights."""
        if not self.enabled:
            return self._weights

        samples = self._collect_training_data()
        if len(samples) < MIN_SAMPLES:
            logger.info(f"StrategyWeighter: only {len(samples)} samples, need {MIN_SAMPLES}")
            return self._weights

        X = np.array([s["features"] for s in samples])
        y = np.array([s["best_strategy"] for s in samples])

        if self._model is None:
            self._model = SGDClassifier(
                loss="log_loss",
                max_iter=1000,
                tol=1e-3,
                random_state=42,
            )
            self._model.fit(X, y)
        else:
            self._model.partial_fit(X, y, classes=STRATEGY_NAMES)

        # Get current market features for weight prediction
        current_features = self._get_current_features()
        if current_features is not None:
            probas = self._model.predict_proba(current_features.reshape(1, -1))[0]
            for i, name in enumerate(self._model.classes_):
                self._weights[name] = float(probas[i])

        self._last_update = datetime.utcnow()
        self._save_model()

        logger.info(f"StrategyWeighter: updated weights: {self._weights}")
        return self._weights.copy()

    def get_weights(self) -> dict[str, float]:
        """Get current strategy weights."""
        return self._weights.copy()

    def get_primary_strategy(self) -> str:
        """Get strategy with highest weight."""
        return max(self._weights, key=self._weights.get)

    def _collect_training_data(self) -> list[dict]:
        """Collect market conditions → best strategy from recent trades."""
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=7)
            trades = db.query(Trade).filter(
                Trade.status == "CLOSED",
                Trade.closed_at >= cutoff,
                Trade.strategy.isnot(None),
            ).order_by(Trade.closed_at).all()

            if not trades:
                return []

            # Group trades by 4-hour windows
            samples = []
            for trade in trades:
                if trade.strategy not in STRATEGY_NAMES:
                    continue

                features = self._get_features_for_trade(trade)
                if features is None:
                    continue

                # Find best strategy in same 4h window
                window_start = trade.closed_at - timedelta(hours=2)
                window_end = trade.closed_at + timedelta(hours=2)
                window_trades = [t for t in trades
                                if t.closed_at and window_start <= t.closed_at <= window_end
                                and t.strategy in STRATEGY_NAMES]

                strategy_pnl = {}
                for wt in window_trades:
                    strategy_pnl[wt.strategy] = strategy_pnl.get(wt.strategy, 0) + wt.net_pnl

                if strategy_pnl:
                    best = max(strategy_pnl, key=strategy_pnl.get)
                    samples.append({
                        "features": features,
                        "best_strategy": best,
                    })

            return samples
        finally:
            db.close()

    def _get_features_for_trade(self, trade) -> np.ndarray | None:
        """Extract 7 features from market conditions at trade time."""
        try:
            raw = self.binance.client.get_klines(
                symbol=f"{trade.symbol}USDT",
                interval="1h",
                limit=250,
            )
            klines = [{
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            } for k in raw]

            indicators = calc_indicators(klines)
            last_vol = klines[-1]["volume"] if klines else 0
            avg_vol = np.mean([k["volume"] for k in klines[-24:]]) if len(klines) >= 24 else last_vol
            volume_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0

            return np.array([
                indicators["adx"],
                indicators["rsi"],
                indicators["atr_pct"],
                volume_ratio,
                trade.closed_at.hour if trade.closed_at else 12,
                trade.closed_at.weekday() if trade.closed_at else 0,
                trade.net_pnl,
            ])
        except Exception as e:
            logger.error(f"StrategyWeighter: failed to extract features: {e}")
            return None

    def _get_current_features(self) -> np.ndarray | None:
        """Get features for current market state."""
        try:
            raw = self.binance.client.get_klines(
                symbol="BTCUSDT",
                interval="1h",
                limit=250,
            )
            klines = [{
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            } for k in raw]

            indicators = calc_indicators(klines)
            last_vol = klines[-1]["volume"] if klines else 0
            avg_vol = np.mean([k["volume"] for k in klines[-24:]]) if len(klines) >= 24 else last_vol
            volume_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0

            now = datetime.utcnow()
            return np.array([
                indicators["adx"],
                indicators["rsi"],
                indicators["atr_pct"],
                volume_ratio,
                now.hour,
                now.weekday(),
                0.0,
            ])
        except Exception as e:
            logger.error(f"StrategyWeighter: failed to get current features: {e}")
            return None

    def get_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "weights": self._weights,
            "primary_strategy": self.get_primary_strategy(),
            "last_update": self._last_update.isoformat() if self._last_update else None,
            "model_trained": self._model is not None,
        }
```
</action>

<acceptance_criteria>
- `from src.learning.strategy_weighter import StrategyWeighter` works
- `StrategyWeighter(binance_client, config)` initializes with equal weights
- `should_update()` returns True when 4+ hours since last update
- `update()` collects training data, trains SGD, returns new weights
- Weights sum to ~1.0
- `get_primary_strategy()` returns strategy with highest weight
- Model persists to disk via pickle
- Handles empty trade history gracefully
</acceptance_criteria>

---

## Task 2.2 — Add pair expansion logic

<read_first>
- src/core/constants.py (CORE_PAIRS)
- src/database/session.py (SessionLocal)
- src/database/models.py (Trade)
- binance_bot_spec_v2.md §3 (trading pairs)
- config.yaml (trading_pairs section)
</read_first>

<action>
1. Update `src/core/constants.py`:

```python
FEE_RATE = 0.001
BREAKEVEN_PCT = 0.002
MIN_TRADE_USDT = 10
DEFAULT_PER_TRADE_USDT = 15
MAX_OPEN_POSITIONS = 7
RESERVED_USDT = 20
CORE_PAIRS = ["BTC", "ETH", "SOL"]
EXTENDED_PAIRS = ["BNB", "XRP", "ADA"]
DOGE_PAIRS = ["DOGE"]
```

2. Create `src/core/pair_manager.py`:

```python
from loguru import logger
from src.core.constants import CORE_PAIRS, EXTENDED_PAIRS, DOGE_PAIRS
from src.database.session import SessionLocal
from src.database.models import Trade


class PairManager:
    """Manages trading pair expansion based on trade history."""

    EXTENDED_AFTER = 50
    DOGE_AFTER = 100

    def __init__(self, config: dict):
        pairs_cfg = config.get("trading_pairs", {})
        self._custom_pairs = pairs_cfg.get("custom", [])

    def get_active_pairs(self) -> list[str]:
        """Return all active trading pairs based on trade count."""
        total_trades = self._count_closed_trades()
        winning_trades = self._count_winning_trades()

        pairs = list(CORE_PAIRS)

        if total_trades >= self.EXTENDED_AFTER:
            pairs.extend(EXTENDED_PAIRS)
            logger.debug(f"PairManager: extended pairs unlocked ({total_trades} trades)")

        if winning_trades >= self.DOGE_AFTER:
            pairs.extend(DOGE_PAIRS)
            logger.debug(f"PairManager: DOGE unlocked ({winning_trades} winning trades)")

        pairs.extend(self._custom_pairs)
        return list(dict.fromkeys(pairs))

    def can_trade_doge(self) -> bool:
        """DOGE only available for Grid after 100+ winning trades."""
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
```
</action>

<acceptance_criteria>
- `from src.core.pair_manager import PairManager` works
- `PairManager(config).get_active_pairs()` returns CORE_PAIRS when < 50 trades
- Returns CORE + EXTENDED when >= 50 trades
- Returns CORE + EXTENDED + DOGE when >= 100 winning trades
- `can_trade_doge()` respects winning trade count
- PairManager is thread-safe (DB per call)
</acceptance_criteria>

---

## Artifacts this plan produces

| File | Purpose |
|------|---------|
| `src/learning/strategy_weighter.py` | SGD online learning for strategy weights |
| `src/core/pair_manager.py` | Pair expansion logic based on trade history |
| `src/core/constants.py` | Updated with EXTENDED_PAIRS, DOGE_PAIRS |
