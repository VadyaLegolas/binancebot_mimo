import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
from loguru import logger


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.testnet = testnet
        self._symbol_info_cache = {}

    def _request_with_retry(self, func, max_retries=3, *args, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                if e.status_code == -1021 and attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue
                raise

    def get_balance(self, asset: str = "USDT") -> float:
        try:
            account = self._request_with_retry(self.client.get_account)
            for balance in account["balances"]:
                if balance["asset"] == asset:
                    return float(balance["free"])
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Binance API error getting balance: {e.status_code} - {e.message}")
            raise

    def get_price(self, symbol: str) -> float:
        try:
            ticker = self._request_with_retry(self.client.get_symbol_ticker, symbol=f"{symbol}USDT")
            return float(ticker["price"])
        except BinanceAPIException as e:
            logger.error(f"Binance API error getting price for {symbol}: {e.status_code} - {e.message}")
            raise