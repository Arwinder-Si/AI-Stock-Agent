from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class MarketDataProvider(Protocol):
    """Fetches NIFTY (or underlying) 5-minute OHLCV in Asia/Kolkata (IST)."""

    def load_ohlcv_5m(
        self,
        symbol: str,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        """
        Return a DataFrame indexed by tz-aware IST timestamps (bar open time).

        Columns: open, high, low, close, volume (lowercase).
        """
        ...
