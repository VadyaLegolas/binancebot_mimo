from binance import ThreadedWebsocketManager
from loguru import logger
from typing import Callable, Optional


class WSManager:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.twm = ThreadedWebsocketManager(api_key=api_key, api_secret=api_secret, testnet=testnet)
        self._streams: dict[str, str] = {}
        self._callbacks: dict[str, Callable] = {}

    def start(self):
        self.twm.start()
        logger.info("WebSocket manager started")

    def stop(self):
        for symbol, stream_name in self._streams.items():
            self.twm.stop_socket(stream_name)
        self.twm.stop()
        self._streams.clear()
        self._callbacks.clear()
        logger.info("WebSocket manager stopped")

    def subscribe_kline(self, symbol: str, interval: str, callback: Callable):
        key = f"{symbol}_{interval}"
        if key in self._streams:
            logger.warning(f"Already subscribed to {key}")
            return
        stream_name = self.twm.start_kline_socket(
            callback=callback,
            symbol=f"{symbol}USDT",
            interval=interval,
        )
        self._streams[key] = stream_name
        self._callbacks[key] = callback
        logger.info(f"Subscribed to {symbol} {interval} klines")

    def subscribe_ticker(self, symbol: str, callback: Callable):
        key = f"{symbol}_ticker"
        if key in self._streams:
            logger.warning(f"Already subscribed to {key}")
            return
        stream_name = self.twm.start_symbol_ticker_socket(
            callback=callback,
            symbol=f"{symbol}USDT",
        )
        self._streams[key] = stream_name
        self._callbacks[key] = callback
        logger.info(f"Subscribed to {symbol} ticker")

    def unsubscribe(self, symbol: str, interval: Optional[str] = None):
        if interval:
            key = f"{symbol}_{interval}"
            if key in self._streams:
                self.twm.stop_socket(self._streams.pop(key))
                self._callbacks.pop(key, None)
        else:
            keys = [k for k in self._streams if k.startswith(f"{symbol}_")]
            for k in keys:
                self.twm.stop_socket(self._streams.pop(k))
                self._callbacks.pop(k, None)
