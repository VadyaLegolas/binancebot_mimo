import numpy as np
import pandas as pd


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = _ema(tr, length)
    plus_di = 100 * _ema(plus_dm, length) / atr.replace(0, np.nan)
    minus_di = 100 * _ema(minus_dm, length) / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = _ema(dx, length)
    return adx


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return _ema(tr, length)


def calc_indicators(klines: list[dict]) -> dict:
    if not klines or len(klines) < 2:
        return {"rsi": 50.0, "ema200": 0.0, "adx": 20.0, "atr": 0.0, "atr_pct": 0.0}

    df = pd.DataFrame(klines)
    last_close = float(df["close"].iloc[-1])

    rsi_val = _rsi(df["close"], 14)
    ema_val = _ema(df["close"], min(200, len(df)))
    adx_val = _adx(df["high"], df["low"], df["close"], 14)
    atr_val = _atr(df["high"], df["low"], df["close"], 14)

    rsi_last = float(rsi_val.iloc[-1]) if not pd.isna(rsi_val.iloc[-1]) else 50.0
    ema_last = float(ema_val.iloc[-1]) if not pd.isna(ema_val.iloc[-1]) else last_close
    adx_last = float(adx_val.iloc[-1]) if not pd.isna(adx_val.iloc[-1]) else 20.0
    atr_last = float(atr_val.iloc[-1]) if not pd.isna(atr_val.iloc[-1]) else 0.0
    atr_pct = (atr_last / last_close * 100) if last_close > 0 and atr_last > 0 else 0.0

    return {
        "rsi": rsi_last,
        "ema200": ema_last,
        "adx": adx_last,
        "atr": atr_last,
        "atr_pct": atr_pct,
    }


def calc_rsi(klines: list[dict], period: int = 14) -> float:
    if not klines or len(klines) < period + 1:
        return 50.0
    df = pd.DataFrame(klines)
    rsi_val = _rsi(df["close"], period)
    return float(rsi_val.iloc[-1]) if not pd.isna(rsi_val.iloc[-1]) else 50.0
