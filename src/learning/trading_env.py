import gymnasium as gym
import numpy as np
from gymnasium import spaces
from src.indicators import calc_indicators
from src.core.constants import FEE_RATE

OBSERVATION_SIZE = 11
ACTION_SPACE_SIZE = 3


class TradingEnv(gym.Env):
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
        return self._get_observation(), {}

    def step(self, action):
        if self._current_step >= len(self._klines) - 1:
            return self._get_observation(), 0.0, True, False, {}

        current_price = self._klines[self._current_step]["close"]
        next_price = self._klines[self._current_step + 1]["close"]
        reward = 0.0

        if action == 1 and self._position == 0:
            fee = self._balance * FEE_RATE
            qty = (self._balance - fee) / current_price
            self._position = qty
            self._entry_price = current_price
            self._entry_step = self._current_step
            self._balance = 0.0
            self._total_fees += fee

        elif action == 2 and self._position > 0:
            sell_total = self._position * current_price
            fee = sell_total * FEE_RATE
            net_pnl = (current_price - self._entry_price) * self._position - fee - (
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
        return self._get_observation(), reward, terminated, False, {}

    def _get_observation(self) -> np.ndarray:
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
        except Exception:
            return [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}] * 1000
