---
wave: 3
depends_on:
  - plan-2-weighter-pairs.md
files_modified:
  - src/learning/trading_env.py
  - src/learning/rl_agent.py
  - src/learning/__init__.py
requirements_addressed:
  - LRN-03
  - LRN-05
autonomous: true
---

# Plan 3 — RL Agent (PPO) + Trading Environment

<objective>
Implement the PPO-based RL Agent using stable-baselines3 with a custom Gymnasium trading environment. The agent observes 11 market features and takes 3 actions (HOLD/BUY/SELL). It supports training (offline), shadow (observe-only), and live (trades) modes. By end of this plan: rl_agent can train on historical data, log shadow decisions, and optionally trade live via /rl on.
</objective>

---

## Task 3.1 — Add stable-baselines3 to requirements

<read_first>
- requirements.txt
</read_first>

<action>
1. Add to `requirements.txt`:
   ```
   stable-baselines3==2.9.0
   gymnasium==1.3.0
   ```
2. Run `pip install stable-baselines3==2.9.0 gymnasium==1.3.0`
</action>

<acceptance_criteria>
- requirements.txt contains stable-baselines3 and gymnasium
- `python -c "import stable_baselines3; import gymnasium"` succeeds
</acceptance_criteria>

---

## Task 3.2 — Create Trading Environment

<read_first>
- src/indicators/__init__.py (calc_indicators)
- src/core/binance_client.py (get_price, client.get_klines)
- src/core/capital.py (calc_pnl)
- src/core/constants.py (FEE_RATE, MIN_TRADE_USDT)
- binance_bot_spec_v2.md §6.3 (RL Agent observation/action space)
</read_first>

<action>
1. Write `src/learning/trading_env.py`:

```python
import gymnasium as gym
import numpy as np
from gymnasium import spaces
from src.indicators import calc_indicators
from src.core.capital import calc_pnl
from src.core.constants import FEE_RATE

OBSERVATION_SIZE = 11
ACTION_SPACE_SIZE = 3  # 0=HOLD, 1=BUY, 2=SELL


class TradingEnv(gym.Env):
    """Custom trading environment for RL agent."""

    metadata = {"render_modes": []}

    def __init__(self, binance_client, symbol: str, initial_balance: float = 100.0):
        super().__init__()
        self.binance = binance_client
        self.symbol = symbol
        self.initial_balance = initial_balance

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(OBSERVATION_SIZE,), dtype=np.float32,
        )
        self.action_space = spaces.Discrete(ACTION_SPACE_SIZE)

        self._klines: list[dict] = []
        self._current_step: int = 0
        self._balance: float = initial_balance
        self._position: float = 0.0
        self._entry_price: float = 0.0
        self._entry_step: int = 0
        self._last_3_pnls: list[float] = [0.0, 0.0, 0.0]
        self._total_fees: float = 0.0
        self._trades: list[dict] = []

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._klines = self._fetch_klines()
        self._current_step = 200
        self._balance = self.initial_balance
        self._position = 0.0
        self._entry_price = 0.0
        self._entry_step = 0
        self._last_3_pnls = [0.0, 0.0, 0.0]
        self._total_fees = 0.0
        self._trades = []

        obs = self._get_observation()
        return obs, {}

    def step(self, action):
        if self._current_step >= len(self._klines) - 1:
            return self._get_observation(), 0.0, True, False, {}

        current_price = self._klines[self._current_step]["close"]
        next_price = self._klines[self._current_step + 1]["close"]
        reward = 0.0

        if action == 1 and self._position == 0:  # BUY
            fee = self._balance * FEE_RATE
            qty = (self._balance - fee) / current_price
            self._position = qty
            self._entry_price = current_price
            self._entry_step = self._current_step
            self._balance = 0.0
            self._total_fees += fee

        elif action == 2 and self._position > 0:  # SELL
            sell_total = self._position * next_price
            fee = sell_total * FEE_RATE
            net_pnl = (next_price - self._entry_price) * self._position - fee - (
                self._entry_price * self._position * FEE_RATE
            )
            self._balance = sell_total - fee
            self._trades.append({
                "entry": self._entry_price,
                "exit": next_price,
                "pnl": net_pnl,
            })
            self._last_3_pnls.append(net_pnl)
            if len(self._last_3_pnls) > 3:
                self._last_3_pnls.pop(0)
            self._total_fees += fee
            self._position = 0.0
            self._entry_price = 0.0

            reward = self._compute_reward(net_pnl)

        self._current_step += 1
        terminated = self._current_step >= len(self._klines) - 1
        truncated = False

        return self._get_observation(), reward, terminated, truncated, {}

    def _get_observation(self) -> np.ndarray:
        """Extract 11 features from current state."""
        window = self._klines[max(0, self._current_step - 200):self._current_step + 1]
        if len(window) < 20:
            return np.zeros(OBSERVATION_SIZE, dtype=np.float32)

        indicators = calc_indicators(window)
        current_price = self._klines[self._current_step]["close"]

        ema_ratio = current_price / indicators["ema200"] if indicators["ema200"] > 0 else 1.0

        vol_window = [k["volume"] for k in self._klines[max(0, self._current_step - 24):self._current_step + 1]]
        avg_vol = np.mean(vol_window) if vol_window else 1.0
        volume_ratio = self._klines[self._current_step]["volume"] / avg_vol if avg_vol > 0 else 1.0

        unrealized_pnl = 0.0
        if self._position > 0:
            unrealized_pnl = (current_price - self._entry_price) / self._entry_price * 100

        time_in_position = (self._current_step - self._entry_step) if self._position > 0 else 0

        total_value = self._balance + self._position * current_price
        balance_pct = total_value / self.initial_balance if self.initial_balance > 0 else 1.0

        last_pnls = self._last_3_pnls + [0.0] * (3 - len(self._last_3_pnls))

        return np.array([
            indicators["rsi"],
            indicators["adx"],
            ema_ratio,
            volume_ratio,
            indicators["atr_pct"],
            unrealized_pnl,
            time_in_position,
            balance_pct,
            last_pnls[0],
            last_pnls[1],
            last_pnls[2],
        ], dtype=np.float32)

    def _compute_reward(self, net_pnl: float) -> float:
        """Compute reward from trade result."""
        profit_reward = net_pnl / self.initial_balance * 100
        fee_penalty = -self._total_fees * 2 / self.initial_balance * 100
        time_penalty = -(self._current_step - self._entry_step) * 0.001
        dd_penalty = 0.0
        if self._position == 0 and self._trades:
            cumulative = sum(t["pnl"] for t in self._trades)
            if cumulative < 0:
                dd_penalty = -abs(cumulative) / self.initial_balance * 100 * 1.5
        return profit_reward + fee_penalty + time_penalty + dd_penalty

    def _fetch_klines(self) -> list[dict]:
        """Fetch historical klines for training."""
        try:
            raw = self.binance.client.get_klines(
                symbol=f"{self.symbol}USDT",
                interval="1h",
                limit=1000,
            )
            return [{
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            } for k in raw]
        except Exception as e:
            logger.error(f"TradingEnv: failed to fetch klines: {e}")
            return [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}] * 1000
```
</action>

<acceptance_criteria>
- `from src.learning.trading_env import TradingEnv` works
- `TradingEnv(binance_client, "BTC")` creates env with correct observation/action spaces
- `reset()` returns observation of shape (11,)
- `step(0)` returns (obs, reward, terminated, truncated, info)
- `step(1)` when no position executes buy
- `step(2)` when position exists executes sell with PnL
- Observation contains all 11 features
- Reward function penalizes fees and drawdown
</acceptance_criteria>

---

## Task 3.3 — Create RL Agent

<read_first>
- src/learning/trading_env.py (TradingEnv)
- src/learning/model_store.py (save_params)
- src/database/session.py (SessionLocal)
- src/database/models.py (Trade, ModelHistory)
- binance_bot_spec_v2.md §6.3 (RL Agent spec)
</read_first>

<action>
1. Write `src/learning/rl_agent.py`:

```python
import os
import json
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
WEEKLY_RETRAIN_STEPS = 10000


class RLAgent:
    """PPO-based RL agent for trading decisions."""

    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        self.config = config
        self._model: PPO | None = None
        self._mode: str = "shadow"  # training, shadow, live
        self._symbol: str = "BTC"
        self._last_train: datetime | None = None
        self._episode_rewards: list[float] = []
        self._consecutive_losses: int = 0
        self._load_model()

    def _load_model(self):
        """Load saved model if exists."""
        os.makedirs(MODEL_DIR, exist_ok=True)
        model_path = os.path.join(MODEL_DIR, "ppo_trading")
        if os.path.exists(f"{model_path}.zip"):
            try:
                self._model = PPO.load(model_path)
                logger.info("RLAgent: loaded model from disk")
            except Exception as e:
                logger.error(f"RLAgent: failed to load model: {e}")

    def _save_model(self):
        """Save model to disk."""
        if self._model:
            model_path = os.path.join(MODEL_DIR, "ppo_trading")
            self._model.save(model_path)
            logger.info("RLAgent: saved model to disk")

    def set_mode(self, mode: str):
        """Set agent mode: training, shadow, or live."""
        if mode in ("training", "shadow", "live"):
            self._mode = mode
            logger.info(f"RLAgent: mode set to {mode}")
        else:
            logger.warning(f"RLAgent: unknown mode {mode}")

    def get_mode(self) -> str:
        return self._mode

    def train(self, symbol: str = "BTC", steps: int = TRAIN_STEPS) -> dict:
        """Train PPO agent on historical data."""
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

        # Evaluate
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
        """Predict action from observation. Returns 0=HOLD, 1=BUY, 2=SELL."""
        if self._model is None:
            return 0
        action, _ = self._model.predict(observation, deterministic=True)
        return int(action)

    def should_retrain(self) -> bool:
        """Check if weekly retraining is due."""
        if not self._last_train:
            return True
        elapsed = datetime.utcnow() - self._last_train
        return elapsed.days >= 7

    def log_decision(self, symbol: str, action: int, observation: np.ndarray):
        """Log decision in shadow mode."""
        action_names = ["HOLD", "BUY", "SELL"]
        logger.debug(f"RLAgent [{self._mode}] {symbol}: {action_names[action]}")

    def record_trade_result(self, pnl: float):
        """Record trade result for consecutive loss tracking."""
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def get_consecutive_losses(self) -> int:
        return self._consecutive_losses

    def _evaluate(self, env, n_episodes: int = 5) -> float:
        """Evaluate agent over n episodes."""
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
```
</action>

<acceptance_criteria>
- `from src.learning.rl_agent import RLAgent` works
- `RLAgent(binance_client, config)` initializes correctly
- `train("BTC", 1000)` trains PPO and saves model
- `predict(obs)` returns 0, 1, or 2
- `set_mode("shadow")` / `set_mode("live")` changes mode
- `should_retrain()` returns True after 7 days
- Model persists to data/rl_models/
- Consecutive losses tracked correctly
</acceptance_criteria>

---

## Artifacts this plan produces

| File | Purpose |
|------|---------|
| `src/learning/trading_env.py` | Gymnasium env with 11-feature observation, 3 actions |
| `src/learning/rl_agent.py` | PPO agent with train/predict/shadow/live modes |
