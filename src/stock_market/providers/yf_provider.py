from __future__ import annotations

import pandas as pd

from stock_market.providers.base import MarketDataProvider


class YFinanceMarketDataProvider:
    """
    Load5m OHLCV via Yahoo Finance (HTTP). No API key.

    NIFTY 50 index ticker is typically ``^NSEI``. Yahoo limits intraday history
    (often ~60 days for 5m); use ``period`` or ``start``/``end`` accordingly.
    """

    def __init__(
        self,
        period: str = "60d",
        interval: str = "5m",
    ) -> None:
        self.period = period
        self.interval = interval

    def load_ohlcv_5m(
        self,
        symbol: str,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        import yfinance as yf

        t = yf.Ticker(symbol)
        if start is not None or end is not None:
            s = start.strftime("%Y-%m-%d") if start is not None else None
            e = end.strftime("%Y-%m-%d") if end is not None else None
            df = t.history(start=s, end=e, interval=self.interval, auto_adjust=False, prepost=False)
        else:
            df = t.history(period=self.period, interval=self.interval, auto_adjust=False, prepost=False)

        if df.empty:
            raise ValueError(f"yfinance returned no rows for {symbol!r} (period={self.period!r}, interval={self.interval!r})")

        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        for c in ("open", "high", "low", "close"):
            if c not in df.columns:
                raise ValueError(f"yfinance data missing {c!r}: {df.columns.tolist()}")
        if "volume" not in df.columns:
            df["volume"] = 0.0

        out = df[["open", "high", "low", "close", "volume"]].astype(float)
        idx = pd.DatetimeIndex(df.index)
        if idx.tz is None:
            out.index = idx.tz_localize("Asia/Kolkata", ambiguous="infer", nonexistent="shift_forward")
        else:
            out.index = idx.tz_convert("Asia/Kolkata")
        out.index.name = "timestamp"
        out = out.sort_index()
        out = out[~out.index.duplicated(keep="last")]
        return out
