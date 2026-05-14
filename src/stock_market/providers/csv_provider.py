from __future__ import annotations

from pathlib import Path

import pandas as pd

from stock_market.providers.base import MarketDataProvider


class CsvMarketDataProvider:
    """
    Load5m OHLCV from CSV.

    Expected columns (case-insensitive): datetime (or timestamp), open, high, low, close, volume.
    Datetimes are parsed as Asia/Kolkata if naive.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load_ohlcv_5m(
        self,
        symbol: str,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        _ = symbol  # unused; single-series CSV
        df = pd.read_csv(self.path)
        df.columns = [c.strip().lower() for c in df.columns]

        time_col = None
        for name in ("datetime", "timestamp", "date", "time"):
            if name in df.columns:
                time_col = name
                break
        if time_col is None:
            raise ValueError(
                f"CSV must have a datetime column (datetime|timestamp|date). Got: {list(df.columns)}"
            )

        for c in ("open", "high", "low", "close", "volume"):
            if c not in df.columns:
                raise ValueError(f"CSV missing column '{c}'. Found: {list(df.columns)}")

        ts = pd.to_datetime(df[time_col], utc=False)
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize("Asia/Kolkata", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert("Asia/Kolkata")

        # Use .values so we do not align on the original RangeIndex (which would yield all NaN).
        out = pd.DataFrame(
            {
                "open": df["open"].astype(float).to_numpy(),
                "high": df["high"].astype(float).to_numpy(),
                "low": df["low"].astype(float).to_numpy(),
                "close": df["close"].astype(float).to_numpy(),
                "volume": df["volume"].astype(float).to_numpy(),
            },
            index=ts.rename("timestamp"),
        )
        out = out.sort_index()
        out = out[~out.index.duplicated(keep="last")]

        if start is not None:
            st = start if start.tzinfo else start.tz_localize("Asia/Kolkata")
            out = out[out.index >= st]
        if end is not None:
            en = end if end.tzinfo else end.tz_localize("Asia/Kolkata")
            out = out[out.index <= en]

        return out
