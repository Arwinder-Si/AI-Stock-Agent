from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP reset each calendar day (index tz Asia/Kolkata)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    vol = df["volume"].replace(0, np.nan)
    pv = tp * df["volume"]
    day = df.index.normalize()
    cum_pv = pv.groupby(day).cumsum()
    cum_v = df["volume"].groupby(day).cumsum()
    vwap = cum_pv / cum_v.replace(0, np.nan)
    return vwap


def rolling_volume_avg(volume: pd.Series, window: int) -> pd.Series:
    return volume.rolling(window, min_periods=max(1, window // 2)).mean()


def ema_slope_abs(ema_series: pd.Series, lookback: int) -> pd.Series:
    """Absolute change in EMA over lookback bars (points)."""
    return (ema_series - ema_series.shift(lookback)).abs()


def vwap_cross_count(close: pd.Series, vwap: pd.Series, window: int) -> pd.Series:
    """
    Count of VWAP crossings in the trailing `window` bars (chop proxy).
    Uses sign change of (close - vwap).
    """
    diff = close - vwap
    sign = np.sign(diff)
    crossed = sign.ne(sign.shift(1)) & sign.shift(1).notna() & (sign != 0)
    return crossed.astype(int).rolling(window, min_periods=1).sum()
