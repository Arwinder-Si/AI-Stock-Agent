from __future__ import annotations

import pandas as pd

from stock_market.providers.base import MarketDataProvider


class StubMarketDataProvider:
    """
    Placeholder provider. Replace with Zerodha/Upstox/etc. by implementing
    `load_ohlcv_5m` and returning IST-indexed 5m bars.
    """

    def load_ohlcv_5m(
        self,
        symbol: str,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "StubMarketDataProvider: plug in a real broker API. "
            "Use CsvMarketDataProvider for offline backtests, or implement "
            "load_ohlcv_5m() to return a DataFrame indexed by IST bar-open times "
            "with columns open, high, low, close, volume."
        )
