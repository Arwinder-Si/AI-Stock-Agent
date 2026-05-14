from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from stock_market.strategy_3pm_breakout import (
    BreakoutConfig,
    Direction,
    TradeSetup,
    evaluate_day,
    exit_deadline_ts,
)


@dataclass
class TradeResult:
    setup: TradeSetup
    exit_ts: pd.Timestamp
    exit_price: float
    outcome: str  # "tp" | "sl" | "time" | "reversal"
    pnl_points: float
    mfe_points: float
    mae_points: float


def _bar_end(ts: pd.Timestamp) -> pd.Timestamp:
    return ts + pd.Timedelta(minutes=5)


def simulate_trade(df_day: pd.DataFrame, setup: TradeSetup, cfg: BreakoutConfig) -> TradeResult:
    """
    From the bar after signal_ts, walk forward until 15:25 bar end.
    Intrabar: stop assumed hit before target if both touched (conservative).
    """
    df_day = df_day.sort_index()
    df_day.index = df_day.index.tz_convert("Asia/Kolkata")

    # Scalper: hard exit at configured time
    deadline = pd.Timestamp(
        year=setup.day.year, 
        month=setup.day.month, 
        day=setup.day.day, 
        hour=cfg.last_exit_bar_end.hour, 
        minute=cfg.last_exit_bar_end.minute, 
        tz="Asia/Kolkata"
    )
    entry = setup.entry_price
    sl = setup.stop_price
    tp = setup.take_profit
    is_long = setup.direction == Direction.LONG

    forward = df_day[df_day.index > setup.signal_ts]
    mfe = 0.0
    mae = 0.0

    for ts, row in forward.iterrows():
        be = _bar_end(ts)
        if be > deadline + pd.Timedelta(seconds=1):
            break

        hi = float(row["high"])
        lo = float(row["low"])
        cl = float(row["close"])

        if is_long:
            mfe = max(mfe, hi - entry)
            mae = max(mae, entry - lo)
            hit_sl = lo <= sl
            hit_tp = hi >= tp
            if hit_sl and hit_tp:
                return TradeResult(
                    setup=setup,
                    exit_ts=ts,
                    exit_price=sl,
                    outcome="sl",
                    pnl_points=sl - entry,
                    mfe_points=mfe,
                    mae_points=mae,
                )
            if hit_sl:
                return TradeResult(
                    setup=setup,
                    exit_ts=ts,
                    exit_price=sl,
                    outcome="sl",
                    pnl_points=sl - entry,
                    mfe_points=mfe,
                    mae_points=mae,
                )
            if hit_tp:
                return TradeResult(
                    setup=setup,
                    exit_ts=ts,
                    exit_price=tp,
                    outcome="tp",
                    pnl_points=tp - entry,
                    mfe_points=mfe,
                    mae_points=mae,
                )
            # Scalper: Exit on reversal candle close
            if cfg.trailing_exit_on_reversal and cl < float(row["open"]):
                return TradeResult(
                    setup=setup,
                    exit_ts=ts,
                    exit_price=cl,
                    outcome="reversal",
                    pnl_points=cl - entry,
                    mfe_points=mfe,
                    mae_points=mae,
                )
        else:
            mfe = max(mfe, entry - lo)
            mae = max(mae, hi - entry)
            hit_sl = hi >= sl
            hit_tp = lo <= tp
            if hit_sl and hit_tp:
                return TradeResult(
                    setup=setup,
                    exit_ts=ts,
                    exit_price=sl,
                    outcome="sl",
                    pnl_points=entry - sl,
                    mfe_points=mfe,
                    mae_points=mae,
                )
            if hit_sl:
                return TradeResult(
                    setup=setup,
                    exit_ts=ts,
                    exit_price=sl,
                    outcome="sl",
                    pnl_points=entry - sl,
                    mfe_points=mfe,
                    mae_points=mae,
                )
            if hit_tp:
                return TradeResult(
                    setup=setup,
                    exit_ts=ts,
                    exit_price=tp,
                    outcome="tp",
                    pnl_points=entry - tp,
                    mfe_points=mfe,
                    mae_points=mae,
                )
            # Scalper: Exit on reversal candle close
            if cfg.trailing_exit_on_reversal and cl > float(row["open"]):
                return TradeResult(
                    setup=setup,
                    exit_ts=ts,
                    exit_price=cl,
                    outcome="reversal",
                    pnl_points=entry - cl,
                    mfe_points=mfe,
                    mae_points=mae,
                )

    # Time exit: last close at or before deadline
    eligible = forward[forward.index.map(lambda t: _bar_end(t) <= deadline)]
    if eligible.empty:
        last_ts = setup.signal_ts
        last_close = setup.signal_close
    else:
        last_ts = eligible.index[-1]
        last_close = float(eligible.iloc[-1]["close"])

    if is_long:
        pnl = last_close - entry
    else:
        pnl = entry - last_close

    return TradeResult(
        setup=setup,
        exit_ts=last_ts,
        exit_price=last_close,
        outcome="time",
        pnl_points=pnl,
        mfe_points=mfe,
        mae_points=mae,
    )


def split_sessions(df: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    """Split by IST calendar date (normalized)."""
    df = df.sort_index()
    if df.index.tz is None:
        idx = df.index.tz_localize("Asia/Kolkata", nonexistent="shift_forward")
    else:
        idx = df.index.tz_convert("Asia/Kolkata")
    df = df.copy()
    df.index = idx
    return {pd.Timestamp(d): group for d, group in df.groupby(idx.normalize())}


def run_backtest(df: pd.DataFrame, cfg: BreakoutConfig) -> tuple[list[TradeResult], list[dict[str, Any]]]:
    trades: list[TradeResult] = []
    skips: list[dict[str, Any]] = []

    for day_norm, df_day in sorted(split_sessions(df).items(), key=lambda x: x[0]):
        setup, reasons = evaluate_day(df_day, cfg)
        if setup is None:
            skips.append({"day": day_norm.isoformat(), "reasons": sorted(set(reasons))})
            continue
        tr = simulate_trade(df_day, setup, cfg)
        trades.append(tr)

    return trades, skips


def trades_to_dataframe(trades: list[TradeResult]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for t in trades:
        s = t.setup
        rows.append(
            {
                "day": s.day.isoformat(),
                "direction": s.direction.value,
                "signal_ts": s.signal_ts.isoformat(),
                "entry": s.entry_price,
                "stop": s.stop_price,
                "tp": s.take_profit,
                "risk": s.risk_points,
                "exit_ts": t.exit_ts.isoformat(),
                "exit_price": t.exit_price,
                "outcome": t.outcome,
                "pnl_points": t.pnl_points,
                "mfe": t.mfe_points,
                "mae": t.mae_points,
            }
        )
    return pd.DataFrame(rows)


def summarize(trades: list[TradeResult]) -> dict[str, Any]:
    if not trades:
        return {"n": 0, "win_rate": None, "total_pnl_points": 0.0, "avg_pnl_points": None}

    pnls = [t.pnl_points for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    return {
        "n": len(trades),
        "win_rate": wins / len(trades),
        "total_pnl_points": float(sum(pnls)),
        "avg_pnl_points": float(sum(pnls) / len(trades)),
        "avg_win": float(sum(p for p in pnls if p > 0) / max(1, wins)) if wins else 0.0,
        "avg_loss": float(sum(p for p in pnls if p <= 0) / max(1, len(trades) - wins)) if len(trades) - wins else 0.0,
    }


