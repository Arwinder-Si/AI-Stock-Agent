from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
from typing import Any, Literal

import pandas as pd

from stock_market.providers.dhan_provider import DhanInstrument, DhanProvider
from stock_market.strategy_3pm_breakout import BreakoutConfig, Direction, TradeSetup, evaluate_day
from stock_market.backtest import split_sessions


@dataclass
class PaperTradeResult:
    day: pd.Timestamp
    direction: str
    option_security_id: str
    qty: int
    entry_ts: pd.Timestamp
    entry_price: float
    exit_ts: pd.Timestamp
    exit_price: float
    outcome: str
    pnl_inr: float


def _next_thursday(d: date) -> date:
    # Monday=0 ... Thursday=3
    days_ahead = (3 - d.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return d + timedelta(days=days_ahead)


def _round_to_step(x: float, step: int) -> int:
    return int(step * round(float(x) / step))


def pick_option_from_chain(
    chain_resp: Any,
    underlying_price: float,
    direction: Direction,
    strike_step: int = 50,
    moneyness: Literal["ATM", "ITM1"] = "ATM",
) -> tuple[str, int] | None:
    """
    Return (security_id, lot_size) for an option to buy.

    This uses Dhan option_chain response. Response formats vary; we try common shapes.
    """
    target_strike = _round_to_step(underlying_price, strike_step)
    if moneyness == "ITM1":
        target_strike = target_strike - strike_step if direction == Direction.LONG else target_strike + strike_step

    want_type = "CE" if direction == Direction.LONG else "PE"

    data = chain_resp.get("data") if isinstance(chain_resp, dict) else chain_resp
    if not data:
        return None

    # Common: list of rows with strike, optionType, securityId, lotSize
    if isinstance(data, list):
        best = None
        for row in data:
            if not isinstance(row, dict):
                continue
            strike = row.get("strikePrice") or row.get("strike") or row.get("strike_price")
            opt_type = row.get("optionType") or row.get("drvOptionType") or row.get("option_type")
            sec = row.get("securityId") or row.get("security_id")
            lot = row.get("lotSize") or row.get("lot_size") or row.get("lot")
            if strike is None or opt_type is None or sec is None:
                continue
            if str(opt_type).upper() not in (want_type, "CALL" if want_type == "CE" else "PUT"):
                continue
            try:
                strike_f = float(strike)
            except Exception:
                continue
            if int(round(strike_f)) != int(target_strike):
                continue
            lot_i = int(lot) if lot is not None else 0
            best = (str(sec), lot_i)
            break
        return best

    return None


def simulate_option_paper_trade(
    option_5m: pd.DataFrame,
    setup_ts: pd.Timestamp,
    premium_sl_pct: float,
    hard_exit_time_ist: tuple[int, int] = (15, 25),
) -> tuple[pd.Timestamp, float, str]:
    """
    Buy option at close of setup bar, exit by SL or time.
    """
    df = option_5m.sort_index()
    df.index = df.index.tz_convert("Asia/Kolkata")
    entry_row = df.loc[setup_ts:setup_ts].iloc[0] if setup_ts in df.index else None
    if entry_row is None:
        raise RuntimeError("Option candles missing entry timestamp")
    entry = float(entry_row["close"])
    sl = entry * (1.0 - premium_sl_pct / 100.0)

    day = setup_ts.normalize()
    deadline = pd.Timestamp(year=day.year, month=day.month, day=day.day, hour=hard_exit_time_ist[0], minute=hard_exit_time_ist[1], tz="Asia/Kolkata")
    forward = df[df.index > setup_ts]
    for ts, row in forward.iterrows():
        if ts > deadline:
            break
        lo = float(row["low"])
        if lo <= sl:
            return ts, sl, "premium_sl"

    eligible = df[df.index <= deadline]
    last_ts = eligible.index[-1]
    last_close = float(eligible.iloc[-1]["close"])
    return last_ts, last_close, "time"


def run_dhan_paper(
    dhan: DhanProvider,
    capital_inr: float,
    start: str,
    end: str,
    premium_sl_pct: float = 20.0,
    moneyness: Literal["ATM", "ITM1"] = "ATM",
) -> list[PaperTradeResult]:
    """
    Paper trade: signal on NIFTY index (via Dhan), buy option premium, one trade/day.
    """
    # NIFTY index instrument for Dhan historical: we rely on security list resolution later; for now use under_security_id=13 via chain.
    # Fetch NIFTY index candles using IDX_I security id 13 if Dhan supports it.
    nifty = DhanInstrument(security_id="13", exchange_segment="IDX_I", instrument_type="INDEX")
    df_idx = dhan.intraday_5m(nifty, f"{start} 09:15:00", f"{end} 15:30:00")

    cfg = BreakoutConfig()
    results: list[PaperTradeResult] = []

    for day_norm, df_day in sorted(split_sessions(df_idx).items(), key=lambda x: x[0]):
        setup, _reasons = evaluate_day(df_day, cfg)
        if setup is None:
            continue

        # Get expiry for that day (next Thursday)
        exp = _next_thursday(day_norm.date())
        chain = dhan.option_chain(exp.strftime("%Y-%m-%d"))
        underlying_px = float(df_day.loc[setup.signal_ts]["close"])
        picked = pick_option_from_chain(chain, underlying_px, setup.direction, moneyness=moneyness)
        if picked is None:
            continue
        sec_id, lot = picked
        if lot <= 0:
            lot = 50  # fallback; broker defines actual lot size

        # Fetch option candles for that day window
        inst = DhanInstrument(security_id=str(sec_id), exchange_segment="NSE_FNO", instrument_type="OPTIDX")
        opt = dhan.intraday_5m(inst, f"{day_norm.date()} 09:15:00", f"{day_norm.date()} 15:30:00")
        if opt.empty or setup.signal_ts not in opt.index:
            continue

        entry_prem = float(opt.loc[setup.signal_ts]["close"])
        cost_per_lot = entry_prem * lot
        if cost_per_lot > capital_inr:
            continue

        exit_ts, exit_px, outcome = simulate_option_paper_trade(opt, setup.signal_ts, premium_sl_pct=premium_sl_pct)
        pnl = (exit_px - entry_prem) * lot
        results.append(
            PaperTradeResult(
                day=day_norm,
                direction=setup.direction.value,
                option_security_id=str(sec_id),
                qty=lot,
                entry_ts=setup.signal_ts,
                entry_price=entry_prem,
                exit_ts=exit_ts,
                exit_price=exit_px,
                outcome=outcome,
                pnl_inr=pnl,
            )
        )

    return results

