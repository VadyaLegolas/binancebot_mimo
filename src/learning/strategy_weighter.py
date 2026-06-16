import numpy as np
from datetime import datetime, timedelta
from loguru import logger
from sklearn.linear_model import SGDClassifier
from src.indicators import calc_indicators
from src.database.session import SessionLocal
from src.database.models import Trade
import json
import os
import threading

WEIGHT_UPDATE_HOURS = 4
MIN_SAMPLES = 20
STRATEGY_NAMES = ["grid", "dca", "rsi_ema", "mtf"]
MODEL_PATH = "data/strategy_weighter.json"


class StrategyWeighter:
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
        self._lock = threading.Lock()
        self._load_model()

    def _load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, "r") as f:
                    data = json.load(f)
                    self._weights = data.get("weights", self._weights)
                    if data.get("last_update"):
                        self._last_update = datetime.fromisoformat(data["last_update"])
                logger.info("StrategyWeighter: загружены веса с диска")
            except Exception as e:
                logger.error(f"StrategyWeighter: ошибка загрузки модели: {e}")

    def _save_model(self):
        os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
        try:
            with open(MODEL_PATH, "w") as f:
                json.dump({
                    "weights": self._weights,
                    "last_update": self._last_update.isoformat() if self._last_update else None,
                }, f, indent=2)
        except Exception as e:
            logger.error(f"StrategyWeighter: failed to save model: {e}")

    def should_update(self) -> bool:
        if not self._last_update:
            return True
        elapsed = datetime.utcnow() - self._last_update
        return elapsed >= timedelta(hours=WEIGHT_UPDATE_HOURS)

    def update(self) -> dict[str, float]:
        if not self.enabled:
            return self._weights

        with self._lock:
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
        return self._weights.copy()

    def get_primary_strategy(self) -> str:
        return max(self._weights, key=self._weights.get)

    def _collect_training_data(self) -> list[dict]:
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

            samples = []
            for trade in trades:
                if trade.strategy not in STRATEGY_NAMES:
                    continue

                features = self._get_features_for_trade(trade)
                if features is None:
                    continue

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
