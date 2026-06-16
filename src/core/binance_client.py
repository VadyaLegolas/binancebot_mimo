from binance.client import Client
from binance.exceptions import BinanceAPIException
from loguru import logger


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.testnet = testnet
        self._symbol_info_cache = {}

    def get_balance(self, asset: str = "USDT") -> float:
        try:
            account = self.client.get_account()
            for balance in account["balances"]:
                if balance["asset"] == asset:
                    return float(balance["free"])
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Binance API error getting balance: {e.status_code} - {e.message}")
            raise

    def get_price(self, symbol: str) -> float:
        try:
            ticker = self.client.get_symbol_ticker(symbol=f"{symbol}USDT")
            return float(ticker["price"])
        except BinanceAPIException as e:
            logger.error(f"Binance API error getting price for {symbol}: {e.status_code} - {e.message}")
            raise

    def get_symbol_info(self, symbol: str) -> dict:
        if symbol not in self._symbol_info_cache:
            try:
                self._symbol_info_cache[symbol] = self.client.get_symbol_info(f"{symbol}USDT")
            except BinanceAPIException as e:
                logger.error(f"Binance API error getting symbol info for {symbol}: {e.status_code} - {e.message}")
                raise
        return self._symbol_info_cache[symbol]

    def get_min_notional(self, symbol: str) -> float:
        info = self.get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "NOTIONAL":
                return float(f["minNotional"])
        return 10.0

    def quantity_precision(self, symbol: str) -> int:
        info = self.get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                step = float(f["stepSize"])
                return len(str(step).rstrip("0").split(".")[-1]) if "." in str(step) else 0
        return 8

    def price_precision(self, symbol: str) -> int:
        info = self.get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "PRICE_FILTER":
                tick = float(f["tickSize"])
                return len(str(tick).rstrip("0").split(".")[-1]) if "." in str(tick) else 0
        return 8

    def get_step_size(self, symbol: str) -> float:
        info = self.get_symbol_info(symbol)
        for f in info["filters"]:
            if f["filterType"] == "LOT_SIZE":
                return float(f["stepSize"])
        return 0.00001

    def place_market_buy(self, symbol: str, quote_qty: float) -> dict:
        try:
            precision = self.quantity_precision(symbol)
            price = self.get_price(symbol)
            qty = round(quote_qty / price, precision)
            return self.client.create_order(
                symbol=f"{symbol}USDT",
                side=Client.SIDE_BUY,
                type=Client.ORDER_TYPE_MARKET,
                quantity=qty,
            )
        except BinanceAPIException as e:
            logger.error(f"Binance API error placing market buy for {symbol}: {e.status_code} - {e.message}")
            raise

    def place_market_sell(self, symbol: str, quantity: float) -> dict:
        try:
            precision = self.quantity_precision(symbol)
            qty = round(quantity, precision)
            return self.client.create_order(
                symbol=f"{symbol}USDT",
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_MARKET,
                quantity=qty,
            )
        except BinanceAPIException as e:
            logger.error(f"Binance API error placing market sell for {symbol}: {e.status_code} - {e.message}")
            raise

    def get_open_orders(self, symbol: str = None) -> list:
        try:
            return self.client.get_open_orders(symbol=f"{symbol}USDT" if symbol else None)
        except BinanceAPIException as e:
            logger.error(f"Binance API error getting open orders: {e.status_code} - {e.message}")
            raise

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        try:
            return self.client.cancel_order(symbol=f"{symbol}USDT", orderId=order_id)
        except BinanceAPIException as e:
            logger.error(f"Binance API error cancelling order {order_id}: {e.status_code} - {e.message}")
            raise
