from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DhanInstrument:
    security_id: str
    exchange_segment: str
    instrument_type: str


class DhanProvider:
    """
    Minimal Dhan helper for paper trading.

    Notes:
    - Access tokens expire; do not hardcode them in code or commit them.
    - We only use data APIs here (no real order placement).
    """

    def __init__(self, client_id: str, access_token: str) -> None:
        from dhanhq import dhanhq
        # Use keyword arguments to avoid positional confusion
        self.dhan = dhanhq(access_token=access_token)

    def option_chain(self, expiry: str) -> Any:
        # Underlying security id for NIFTY in Dhan examples is often 13.
        # We keep this constant and use Dhan's option_chain to get strikes.
        return self.dhan.option_chain(under_security_id=13, under_exchange_segment="IDX_I", expiry=expiry)

    def intraday_5m(self, inst: DhanInstrument, from_date: str, to_date: str) -> pd.DataFrame:
        """
        Fetch 5m candles via Dhan intraday historical data.

        Dhan's python client exposes `intraday_minute_data(...)` (last few days) and v2 intraday chart endpoints.
        This wrapper uses `intraday_minute_data` when available with from/to.
        """
        fn = getattr(self.dhan, "intraday_minute_data", None)
        if fn is None:
            raise RuntimeError("Installed dhanhq client does not expose intraday_minute_data()")

        resp = fn(inst.security_id, inst.exchange_segment, inst.instrument_type, from_date, to_date)
        if isinstance(resp, dict):
            # Dhan can return different status strings; treat any failure as an error.
            status = str(resp.get("status", "")).lower()
            if status in ("error", "failure", "failed"):
                remarks = resp.get("remarks") or resp.get("data") or resp
                raise RuntimeError(
                    "Dhan data API call failed. "
                    "This usually means Data APIs/Trading APIs access is not enabled for your account. "
                    f"Details: {remarks}"
                )

        # Dhan responses vary; attempt to normalize to a candle table.
        data = resp.get("data") if isinstance(resp, dict) else resp
        if not data:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        # Some failures come back as a dict inside `data`.
        if isinstance(data, dict) and any(k in data for k in ("errorCode", "errorMessage", "errorType")):
            raise RuntimeError(
                "Dhan returned an error payload instead of candles. "
                "Enable DhanHQ Trading APIs + subscribe to Data APIs, then regenerate your access token. "
                f"Details: {data}"
            )

        # Common format: {'open':[...], 'high':[...], ... , 'timestamp':[...]} or list of dicts
        if isinstance(data, dict) and all(k in data for k in ("open", "high", "low", "close")):
            ts_key = "timestamp" if "timestamp" in data else ("time" if "time" in data else None)
            if ts_key is None:
                raise RuntimeError(f"Unknown candle timestamp key in response: {list(data.keys())}")
            df = pd.DataFrame(
                {
                    "open": data["open"],
                    "high": data["high"],
                    "low": data["low"],
                    "close": data["close"],
                    "volume": data.get("volume", [0] * len(data["close"])),
                    "ts": data[ts_key],
                }
            )
            idx = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
            out = df.drop(columns=["ts"]).astype(float)
            out.index = idx.rename("timestamp")
            return out.sort_index()

        if isinstance(data, list):
            df = pd.DataFrame(data)
            df.columns = [c.lower() for c in df.columns]
            ts_col = "timestamp" if "timestamp" in df.columns else ("time" if "time" in df.columns else None)
            if ts_col is None:
                raise RuntimeError(f"Unknown candle timestamp column in response: {df.columns.tolist()}")
            idx = pd.to_datetime(df[ts_col], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
            out = df.rename(
                columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
            )
            for c in ("open", "high", "low", "close"):
                if c not in out.columns:
                    raise RuntimeError(f"Missing candle column {c!r} in response columns: {out.columns.tolist()}")
            if "volume" not in out.columns:
                out["volume"] = 0.0
            out = out[["open", "high", "low", "close", "volume"]].astype(float)
            out.index = idx.rename("timestamp")
            return out.sort_index()

        raise RuntimeError(f"Unsupported Dhan candle response shape: {type(data)}")

