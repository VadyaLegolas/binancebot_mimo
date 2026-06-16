from loguru import logger
from src.indicators import calc_indicators


class AutoSelector:
    def __init__(self, binance_client, config: dict):
        self.binance = binance_client
        self.enabled = config.get("auto_selector", {}).get("enabled", True)
        self._current_strategy: str | None = None

    def select(self, symbol: str) -> str:
        if not self.enabled:
            return self._current_strategy or "grid"

        try:
            indicators = self._get_market_indicators(symbol)
        except Exception as e:
            logger.error(f"AutoSelector: failed to get indicators for {symbol}: {e}")
            return self._current_strategy or "grid"

        adx = indicators["adx"]
        rsi = indicators["rsi"]

        if adx < 20:
            strategy = "grid"
        elif adx < 35:
            if rsi < 35:
                strategy = "dca"
            else:
                strategy = "rsi_ema"
        else:
            strategy = "mtf"

        if strategy != self._current_strategy:
            logger.info(f"AutoSelector {symbol}: {self._current_strategy} -> {strategy} (ADX={adx:.1f}, RSI={rsi:.1f})")
            self._current_strategy = strategy

        return strategy

    def _get_market_indicators(self, symbol: str) -> dict:
        raw = self.binance.client.get_klines(
            symbol=f"{symbol}USDT",
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
        return calc_indicators(klines)

    def get_current_strategy(self) -> str | None:
        return self._current_strategy
