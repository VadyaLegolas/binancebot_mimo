from src.strategies.base import BaseStrategy, Signal, TradeAction
from src.strategies.grid import GridStrategy
from src.strategies.dca import DCAStrategy
from src.strategies.rsi_ema import RSIEMAStrategy
from src.strategies.mtf import MTFMomentumStrategy

ALL_STRATEGIES = {
    "grid": GridStrategy,
    "dca": DCAStrategy,
    "rsi_ema": RSIEMAStrategy,
    "mtf": MTFMomentumStrategy,
}
