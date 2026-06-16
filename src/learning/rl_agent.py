import os
import numpy as np
from datetime import datetime
from loguru import logger
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from src.learning.trading_env import TradingEnv
from src.learning.model_store import save_params
from src.database.session import SessionLocal
from src.database.models import Trade

MODEL_DIR = "data/rl_models"
TRAIN_STEPS = 10000


class RLAgent:
    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        self.config = config
        self._model: PPO | None = None
        self._mode: str = "shadow"
        self._symbol: str = "BTC"
        self._last_train: datetime | None = None
        self._consecutive_losses: int = 0
        self._load_model()

    def _load_model(self):
        os.makedirs(MODEL_DIR, exist_ok=True)
        model_path = os.path.join(MODEL_DIR, "ppo_trading")
        if os.path.exists(f"{model_path}.zip"):
            try:
                self._model = PPO.load(model_path)
                logger.info("RLAgent: loaded model from disk")
            except Exception as e:
                logger.error(f"RLAgent: failed to load model: {e}")

    def _save_model(self):
        if self._model:
            model_path = os.path.join(MODEL_DIR, "ppo_trading")
            self._model.save(model_path)
            logger.info("RLAgent: saved model to disk")

    def set_mode(self, mode: str):
        if mode in ("training", "shadow", "live"):
            self._mode = mode
            logger.info(f"RLAgent: mode set to {mode}")

    def get_mode(self) -> str:
        return self._mode

    def train(self, symbol: str = "BTC", steps: int = TRAIN_STEPS) -> dict:
        self._symbol = symbol
        env = TradingEnv(self.binance, symbol)
        vec_env = DummyVecEnv([lambda: env])

        if self._model is None:
            self._model = PPO(
                "MlpPolicy",
                vec_env,
                verbose=0,
                learning_rate=3e-4,
                n_steps=2048,
                batch_size=64,
                n_epochs=10,
            )
        else:
            self._model.set_env(vec_env)

        self._model.learn(total_timesteps=steps)
        self._last_train = datetime.utcnow()
        self._save_model()

        mean_reward = self._evaluate(vec_env, n_episodes=5)

        save_params(
            strategy="rl_agent",
            model_type="rl_agent",
            params_before={},
            params_after={"steps": steps, "symbol": symbol},
            metrics={"sharpe_after": mean_reward, "applied": True},
        )

        logger.info(f"RLAgent: trained on {symbol}, mean reward: {mean_reward:.2f}")
        return {"mean_reward": mean_reward, "steps": steps, "symbol": symbol}

    def predict(self, observation: np.ndarray) -> int:
        if self._model is None:
            return 0
        action, _ = self._model.predict(observation, deterministic=True)
        return int(action)

    def should_retrain(self) -> bool:
        if not self._last_train:
            return True
        elapsed = datetime.utcnow() - self._last_train
        return elapsed.days >= 7

    def log_decision(self, symbol: str, action: int, observation: np.ndarray):
        action_names = ["HOLD", "BUY", "SELL"]
        logger.debug(f"RLAgent [{self._mode}] {symbol}: {action_names[action]}")

    def record_trade_result(self, pnl: float):
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def get_consecutive_losses(self) -> int:
        return self._consecutive_losses

    def _evaluate(self, env, n_episodes: int = 5) -> float:
        total_rewards = []
        for _ in range(n_episodes):
            obs, _ = env.reset()
            done = False
            total_reward = 0.0
            while not done:
                action, _ = self._model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, _ = env.step(action)
                total_reward += reward
                done = terminated or truncated
            total_rewards.append(total_reward)
        return float(np.mean(total_rewards))

    def get_status(self) -> dict:
        return {
            "mode": self._mode,
            "model_loaded": self._model is not None,
            "last_train": self._last_train.isoformat() if self._last_train else None,
            "consecutive_losses": self._consecutive_losses,
            "should_retrain": self.should_retrain(),
        }
