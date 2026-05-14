from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import Enum
import pandas as pd

from stock_market.indicators import (
    ema,
    ema_slope_abs,
    rolling_volume_avg,
    session_vwap,
    vwap_cross_count,
)


class StopMode(str, Enum):
    OPPOSITE_SIDE = "opposite_side"
    HALF_REF_RANGE = "half_ref_range"


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class BreakoutConfig:
    """Tunable thresholds; defaults align with playbook 'PRO' filters."""

    ref_open_time: time = time(14, 55)
    entry_open_times: tuple[time, ...] = (time(15, 0), time(15, 5))
    last_exit_bar_end: time = time(15, 25)
    ema_span: int = 20
    volume_avg_window: int = 12
    volume_min_mult: float = 1.0
    min_ref_range_points: float = 5.0
    ema_flat_lookback: int = 6
    ema_flat_max_slope: float = 2.0
    vwap_chop_window: int = 18
    vwap_chop_max_crosses: int = 8
    min_body_frac_of_range: float = 0.35
    max_vwap_deviation_frac: float = 0.012
    reward_r_min: float = 1.2
    reward_r_max: float = 1.5
    reward_r: float = 1.35
    stop_mode: StopMode = StopMode.OPPOSITE_SIDE
    slippage_points: float = 0.5
    strict_expiry: bool = False
    expiry_weekdays: tuple[int, ...] = (1,)  # Monday=0 … Tuesday=1 (NIFTY weekly)
    require_vwap_ema_align: bool = True
    
    # Scalper Filters
    require_trend_align: bool = False  # Long only if session is UP
    max_dist_from_extreme_pct: float = 1.0  # Max distance from DH/DL to allow trade
    min_vix_level: float = 0.0  # Only trade if VIX is above this
    
    # Advanced Scalper Improvements
    require_orb_confluence: bool = False  # Trade must break the 09:15-09:45 range
    min_volume_acceleration: float = 0.0   # 15:00 Vol must be X times 14:55 Vol (e.g. 1.5)
    max_stop_points: float = 0.0           # Max points to risk; if exceeded, SL moved to 50% of ref candle
    trailing_exit_on_reversal: bool = False # Exit if a candle closes against the trade


@dataclass
class ReferenceCandle:
    ts_open: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def range_points(self) -> float:
        return float(self.high - self.low)


@dataclass
class TradeSetup:
    day: pd.Timestamp
    direction: Direction
    ref: ReferenceCandle
    signal_ts: pd.Timestamp
    signal_close: float
    entry_price: float
    stop_price: float
    take_profit: float
    risk_points: float
    day_high: float = 0.0
    day_low: float = 0.0
    trend_pct: float = 0.0
    reasons_ok: list[str] = field(default_factory=list)


def _ist_date(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.tz_convert("Asia/Kolkata").normalize()


def _bar_matches_open_time(ts: pd.Timestamp, target: time) -> bool:
    """Match5m bar open clock in Asia/Kolkata (hour + minute)."""
    t = ts.tz_convert("Asia/Kolkata")
    return t.hour == target.hour and t.minute == target.minute


def find_reference_candle(df_day: pd.DataFrame, cfg: BreakoutConfig) -> ReferenceCandle | None:
    """Bar indexed by open time 14:55 IST."""
    mask = df_day.index.map(lambda t: _bar_matches_open_time(pd.Timestamp(t), cfg.ref_open_time))
    rows = df_day.loc[mask]
    if rows.empty:
        return None
    r = rows.iloc[0]
    ts = rows.index[0]
    return ReferenceCandle(
        ts_open=ts,
        open=float(r["open"]),
        high=float(r["high"]),
        low=float(r["low"]),
        close=float(r["close"]),
        volume=float(r["volume"]),
    )


def _stop_price(direction: Direction, ref: ReferenceCandle, cfg: BreakoutConfig) -> float:
    rng = ref.range_points
    if cfg.stop_mode == StopMode.OPPOSITE_SIDE:
        return ref.low if direction == Direction.LONG else ref.high
    mid = ref.low + 0.5 * rng
    return mid


def _body_frac(row: pd.Series) -> float:
    o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    rng = h - l
    if rng <= 0:
        return 0.0
    return abs(c - o) / rng


def _is_expiry_day(day_norm: pd.Timestamp, cfg: BreakoutConfig) -> bool:
    wd = int(day_norm.weekday())
    return wd in cfg.expiry_weekdays


def evaluate_skip_filters(
    row: pd.Series,
    ref: ReferenceCandle,
    df_day: pd.DataFrame,
    cfg: BreakoutConfig,
    context: dict[str, float] | None = None,
) -> list[str]:
    """Return list of skip reason codes; empty means filters passed."""
    reasons: list[str] = []
    ts = row.name
    if not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    ts = ts.tz_convert("Asia/Kolkata")

    if ref.range_points < cfg.min_ref_range_points:
        reasons.append("REF_TOO_SMALL")

    ema20 = ema(df_day["close"], cfg.ema_span)
    slope = ema_slope_abs(ema20, cfg.ema_flat_lookback)
    vwap = session_vwap(df_day)
    vol_avg = rolling_volume_avg(df_day["volume"], cfg.volume_avg_window)

    slope_here = slope.loc[ts]
    if pd.isna(slope_here):
        reasons.append("EMA_NA")
    elif float(slope_here) < cfg.ema_flat_max_slope:
        reasons.append("EMA_FLAT")

    vwap_here = float(vwap.loc[ts])
    crosses = vwap_cross_count(df_day["close"], vwap, cfg.vwap_chop_window)
    if float(crosses.loc[ts]) > cfg.vwap_chop_max_crosses:
        reasons.append("VWAP_CHOP")

    close = float(row["close"])
    if not pd.isna(vwap_here) and vwap_here > 0:
        if abs(close - vwap_here) / vwap_here > cfg.max_vwap_deviation_frac:
            reasons.append("OVEREXTENDED_VWAP")

    if _body_frac(row) < cfg.min_body_frac_of_range:
        reasons.append("WEAK_BODY")

    vol = float(row["volume"])
    va = float(vol_avg.loc[ts])
    day_has_volume = float(df_day["volume"].sum()) > 0
    if day_has_volume and va > 0 and vol < cfg.volume_min_mult * va:
        reasons.append("LOW_VOLUME")

    day_norm = _ist_date(ts)
    if cfg.strict_expiry and _is_expiry_day(day_norm, cfg):
        reasons.append("EXPIRY_STRICT_SKIP")

    # Scalper Context Filters
    if context:
        dh = context.get("day_high", 0.0)
        dl = context.get("day_low", 1e9)
        trend_pct = context.get("trend_pct", 0.0)
        orb_h = context.get("orb_high", 0.0)
        orb_l = context.get("orb_low", 1e9)
        
        # Trend alignment (Pro Scalper: only trade with the wind)
        is_long_signal = close > ref.high
        if cfg.require_trend_align:
            if is_long_signal and trend_pct < 0:
                reasons.append("TREND_MISALIGN_LONG")
            if not is_long_signal and trend_pct > 0:
                reasons.append("TREND_MISALIGN_SHORT")
        
        # Proximity to extremes (Pro Scalper: breakout from extremes is high probability)
        if cfg.max_dist_from_extreme_pct < 1.0:
            if is_long_signal:
                dist_pct = (dh - close) / close * 100.0 if dh > close else 0.0
                if dist_pct > cfg.max_dist_from_extreme_pct:
                    reasons.append("FAR_FROM_DAY_HIGH")
            else:
                dist_pct = (close - dl) / close * 100.0 if close > dl else 0.0
                if dist_pct > cfg.max_dist_from_extreme_pct:
                    reasons.append("FAR_FROM_DAY_LOW")

        # ORB Confluence
        if cfg.require_orb_confluence:
            if is_long_signal and close <= orb_h:
                reasons.append("NOT_BREAKING_ORB_HIGH")
            if not is_long_signal and close >= orb_l:
                reasons.append("NOT_BREAKING_ORB_LOW")

        # Volume Acceleration
        if cfg.min_volume_acceleration > 0:
            ref_vol = ref.volume
            cur_vol = float(row["volume"])
            if ref_vol > 0 and cur_vol < cfg.min_volume_acceleration * ref_vol:
                reasons.append("LOW_VOL_ACCELERATION")

    return reasons


def directional_alignment(direction: Direction, row: pd.Series, df_day: pd.DataFrame, cfg: BreakoutConfig) -> bool:
    ts = row.name
    ema20 = ema(df_day["close"], cfg.ema_span)
    vwap = session_vwap(df_day)
    close = float(row["close"])
    ema_here = float(ema20.loc[ts])
    vwap_here = float(vwap.loc[ts])

    vwap_ok = True
    if not pd.isna(vwap_here):
        if direction == Direction.LONG:
            vwap_ok = close >= vwap_here
        else:
            vwap_ok = close <= vwap_here

    if direction == Direction.LONG:
        return vwap_ok and close >= ema_here
    return vwap_ok and close <= ema_here


def evaluate_day(
    df_day: pd.DataFrame,
    cfg: BreakoutConfig,
) -> tuple[TradeSetup | None, list[str]]:
    """
    First confirmed close breakout in 15:00/15:05 bars, after filters.
    Returns (setup, skip_reasons_if_no_trade).
    """
    if df_day.empty:
        return None, ["EMPTY_DAY"]

    df_day = df_day.sort_index()
    idx_ist = df_day.index.tz_convert("Asia/Kolkata")
    df_day = df_day.copy()
    df_day.index = idx_ist

    # Opening Range (09:15-09:45)
    orb_bars = df_day[(df_day.index.hour == 9) & (df_day.index.minute >= 15) & (df_day.index.minute <= 40)]
    if orb_bars.empty:
        orb_high, orb_low = 0.0, 1e9
    else:
        orb_high = orb_bars["high"].max()
        orb_low = orb_bars["low"].min()

    # Session context up to reference candle
    pre_3pm = df_day[df_day.index < pd.Timestamp(df_day.index[0].normalize().year, df_day.index[0].normalize().month, df_day.index[0].normalize().day, 14, 55, tz="Asia/Kolkata")]
    if pre_3pm.empty:
        day_high = df_day["high"].max()
        day_low = df_day["low"].min()
        session_open = df_day["open"].iloc[0]
    else:
        day_high = pre_3pm["high"].max()
        day_low = pre_3pm["low"].min()
        session_open = pre_3pm["open"].iloc[0]

    ref = find_reference_candle(df_day, cfg)
    if ref is None:
        return None, ["NO_REF_CANDLE"]
    
    trend_pct = (ref.close - session_open) / session_open * 100.0
    context = {
        "day_high": day_high,
        "day_low": day_low,
        "trend_pct": trend_pct,
        "orb_high": orb_high,
        "orb_low": orb_low
    }

    if ref.range_points < cfg.min_ref_range_points:
        return None, ["REF_TOO_SMALL"]

    entry_mask = df_day.index.map(
        lambda t: any(_bar_matches_open_time(pd.Timestamp(t), ot) for ot in cfg.entry_open_times)
    )
    entry_bars = df_day.loc[entry_mask].sort_index()

    skip_log: list[str] = []

    for ts, row in entry_bars.iterrows():
        c = float(row["close"])
        long_ok = c > ref.high
        short_ok = c < ref.low

        if long_ok and short_ok:
            skip_log.append("CONFLICT_DIRECTION")
            continue
        if not long_ok and not short_ok:
            continue

        d = Direction.LONG if long_ok else Direction.SHORT

        if cfg.require_vwap_ema_align and not directional_alignment(d, row, df_day, cfg):
            skip_log.append("VWAP_EMA_NOT_ALIGNED")
            continue

        filt = evaluate_skip_filters(row, ref, df_day, cfg, context=context)
        if filt:
            skip_log.extend(filt)
            continue

        # Stop Loss Logic
        sl = _stop_price(d, ref, cfg)
        risk = abs(c - sl)
        
        # Risk Cap Logic for Scalpers
        if cfg.max_stop_points > 0 and risk > cfg.max_stop_points:
            # Move SL to 50% of reference candle range
            sl = (ref.high + ref.low) / 2.0
            risk = abs(c - sl)
            # Re-check directionality
            if d == Direction.LONG and c <= sl: continue
            if d == Direction.SHORT and c >= sl: continue

        if risk <= 0:
            skip_log.append("ZERO_RISK")
            continue

        if long_ok and c <= sl:
            skip_log.append("STOP_INVALID_LONG")
            continue
        if short_ok and c >= sl:
            skip_log.append("STOP_INVALID_SHORT")
            continue

        entry = c + cfg.slippage_points if long_ok else c - cfg.slippage_points
        r = cfg.reward_r
        if long_ok:
            tp = entry + r * abs(entry - sl)
        else:
            tp = entry - r * abs(entry - sl)

        setup = TradeSetup(
            day=_ist_date(ts),
            direction=d,
            ref=ref,
            signal_ts=ts,
            signal_close=c,
            entry_price=entry,
            stop_price=sl,
            take_profit=tp,
            risk_points=float(abs(entry - sl)),
            day_high=day_high,
            day_low=day_low,
            trend_pct=trend_pct,
            reasons_ok=["CLOSE_CONFIRMED", "BODY_OK", "VOL_OK", "ALIGN_OK", "CONTEXT_OK"],
        )
        return setup, []

    if not skip_log:
        skip_log.append("NO_BREAKOUT")
    return None, skip_log


def entry_window_end_ts(day_norm: pd.Timestamp) -> pd.Timestamp:
    """Last moment of entry window (15:10) for sanity checks."""
    d = day_norm.tz_convert("Asia/Kolkata")
    return pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=15, minute=10, tz="Asia/Kolkata")


def exit_deadline_ts(day_norm: pd.Timestamp) -> pd.Timestamp:
    d = day_norm.tz_convert("Asia/Kolkata")
    return pd.Timestamp(year=d.year, month=d.month, day=d.day, hour=15, minute=25, tz="Asia/Kolkata")
