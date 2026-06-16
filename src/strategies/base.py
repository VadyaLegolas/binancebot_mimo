from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeAction:
    signal: Signal
    symbol: str
    quantity: float | None = None
    quote_qty: float | None = None
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def analyze(self, symbol: str, klines: list[dict], current_price: float,
                open_positions: list) -> TradeAction:
        ...

    @abstractmethod
    def get_params(self) -> dict:
        ...

    @abstractmethod
    def set_params(self, params: dict) -> None:
        ...

    def on_fill(self, symbol: str, side: str, price: float, quantity: float) -> None:
        pass
