from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from stock_market.backtest import run_backtest, summarize, trades_to_dataframe
from stock_market.paper_dhan import run_dhan_paper
from stock_market.providers.csv_provider import CsvMarketDataProvider
from stock_market.providers.stub_provider import StubMarketDataProvider
from stock_market.providers.dhan_provider import DhanProvider
from stock_market.providers.yf_provider import YFinanceMarketDataProvider
from stock_market.strategy_3pm_breakout import BreakoutConfig, StopMode


def _cfg_from_args(ns: argparse.Namespace) -> BreakoutConfig:
    from datetime import datetime
    exit_t = datetime.strptime(ns.exit_time, "%H:%M").time()
    
    return BreakoutConfig(
        slippage_points=ns.slippage,
        reward_r=ns.reward_r,
        stop_mode=StopMode(ns.stop_mode),
        strict_expiry=ns.strict_expiry,
        min_ref_range_points=ns.min_ref_range,
        volume_min_mult=ns.volume_mult,
        max_vwap_deviation_frac=ns.max_vwap_dev,
        ema_flat_max_slope=ns.ema_flat_max_slope,
        vwap_chop_max_crosses=ns.vwap_chop_max,
        require_vwap_ema_align=not ns.no_vwap_ema_align,
        require_trend_align=ns.require_trend_align,
        max_dist_from_extreme_pct=ns.max_dist_extreme_pct,
        require_orb_confluence=ns.require_orb,
        min_volume_acceleration=ns.vol_accel,
        max_stop_points=ns.max_sl,
        trailing_exit_on_reversal=ns.trail_reversal,
        last_exit_bar_end=exit_t,
    )


def cmd_backtest(ns: argparse.Namespace) -> int:
    if ns.provider == "stub":
        provider: StubMarketDataProvider | CsvMarketDataProvider | YFinanceMarketDataProvider = (
            StubMarketDataProvider()
        )
    elif ns.provider == "yfinance":
        provider = YFinanceMarketDataProvider(period=ns.yf_period, interval="5m")
    else:
        if not ns.csv:
            print("error: --csv is required when --provider csv", file=sys.stderr)
            return 2
        provider = CsvMarketDataProvider(ns.csv)

    cfg = _cfg_from_args(ns)
    start = pd.Timestamp(ns.start) if ns.start else None
    end = pd.Timestamp(ns.end) if ns.end else None
    if start is not None and start.tzinfo is None:
        start = start.tz_localize("Asia/Kolkata")
    if end is not None and end.tzinfo is None:
        end = end.tz_localize("Asia/Kolkata")
    df = provider.load_ohlcv_5m(ns.symbol, start=start, end=end)
    trades, skips = run_backtest(df, cfg)

    out_dir = Path(ns.output_dir) if ns.output_dir else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    trades_path = out_dir / "trades.csv"
    skips_path = out_dir / "skips.json"
    metrics_path = out_dir / "metrics.json"

    if trades:
        trades_to_dataframe(trades).to_csv(trades_path, index=False)
    else:
        trades_path.write_text("day,direction,signal_ts,entry,stop,tp,risk,exit_ts,exit_price,outcome,pnl_points,mfe,mae\n", encoding="utf-8")

    skips_path.write_text(json.dumps(skips, indent=2), encoding="utf-8")
    metrics = summarize(trades)
    if ns.capital_inr is not None and ns.max_risk_pct is not None:
        max_risk_inr = float(ns.capital_inr) * (float(ns.max_risk_pct) / 100.0)
        metrics["capital_inr"] = float(ns.capital_inr)
        metrics["max_risk_pct"] = float(ns.max_risk_pct)
        metrics["max_risk_inr"] = max_risk_inr
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"Wrote {trades_path}, {skips_path}, {metrics_path}")
    print(json.dumps(metrics, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stock-market", description="NIFTY 3PM breakout toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backtest", help="Run index-point backtest from CSV, Yahoo Finance, or stub")
    b.add_argument("--provider", choices=("csv", "stub", "yfinance"), default="csv")
    b.add_argument("--csv", type=Path, default=None, help="Path to OHLCV CSV")
    b.add_argument(
        "--symbol",
        default="^NSEI",
        help="Ticker for yfinance (default ^NSEI = NIFTY 50); CSV ignores",
    )
    b.add_argument(
        "--yf-period",
        default="60d",
        help="yfinance period when --start/--end not set (5m data is limited, e.g. 60d)",
    )
    b.add_argument("--start", default=None, help="Optional start date YYYY-MM-DD (yfinance)")
    b.add_argument("--end", default=None, help="Optional end date YYYY-MM-DD (yfinance)")
    b.add_argument("--output-dir", type=Path, default=Path("out"))
    b.add_argument("--slippage", type=float, default=0.5)
    b.add_argument("--reward-r", type=float, default=1.35)
    b.add_argument("--stop-mode", choices=[m.value for m in StopMode], default=StopMode.OPPOSITE_SIDE.value)
    b.add_argument("--strict-expiry", action="store_true")
    b.add_argument("--min-ref-range", type=float, default=5.0)
    b.add_argument("--volume-mult", type=float, default=1.0)
    b.add_argument("--max-vwap-dev", type=float, default=0.012)
    b.add_argument("--ema-flat-max-slope", type=float, default=2.0)
    b.add_argument("--vwap-chop-max", type=int, default=8)
    b.add_argument(
        "--no-vwap-ema-align",
        action="store_true",
        help="Skip VWAP+EMA direction filter",
    )
    b.add_argument("--require-trend-align", action="store_true", help="Long only if day is UP, Short only if day is DOWN")
    b.add_argument("--max-dist-extreme-pct", type=float, default=1.0, help="Max distance (%) from Day High/Low for entry")
    b.add_argument("--require-orb", action="store_true", help="Trade must break the 09:15-09:45 Opening Range")
    b.add_argument("--vol-accel", type=float, default=0.0, help="Min volume multiplier relative to ref candle (e.g. 1.5)")
    b.add_argument("--max-sl", type=float, default=0.0, help="Max stop-loss points; if exceeded, SL moved to 50%% of ref candle")
    b.add_argument("--trail-reversal", action="store_true", help="Exit if a 5m candle closes against the trade")
    b.add_argument("--exit-time", default="15:25", help="Hard exit time HH:MM (e.g. 15:10 for scalpers)")
    b.add_argument(
        "--capital-inr",
        type=float,
        default=None,
        help="Optional: capital sleeve in INR (for journaling only; backtest P&L remains in points)",
    )
    b.add_argument(
        "--max-risk-pct",
        type=float,
        default=None,
        help="Optional: daily risk cap as percent of --capital-inr (for journaling only)",
    )
    b.set_defaults(func=cmd_backtest)

    agent = sub.add_parser("agent", help="Get a trade recommendation for a specific date")
    agent.add_argument("--nifty-csv", required=True)
    agent.add_argument("--bank-csv", required=True)
    agent.add_argument("--vix-csv")
    agent.add_argument("--date", required=True, help="Date to analyze (YYYY-MM-DD)")
    agent.set_defaults(func=cmd_agent)

    paper = sub.add_parser("paper", help="Dhan paper trading (options premium INR P&L)")
    paper.add_argument("--client-id", default=None, help="Dhan client id (or set DHAN_CLIENT_ID env var)")
    paper.add_argument("--access-token", default=None, help="Dhan access token (or set DHAN_ACCESS_TOKEN env var)")
    paper.add_argument("--capital-inr", type=float, default=10000.0)
    paper.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    paper.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    paper.add_argument("--premium-sl-pct", type=float, default=20.0, help="Premium stop loss percent for option buying")
    paper.add_argument("--moneyness", choices=("ATM", "ITM1"), default="ATM")
    paper.add_argument("--output", type=Path, default=Path("out_paper_dhan.json"))
    paper.set_defaults(func=cmd_paper)

    return p


def _env_get(key: str) -> str | None:
    import os

    v = os.getenv(key)
    if v:
        return v
    # tiny .env fallback for local use (do not commit secrets)
    env_path = Path("src") / ".env"
    if not env_path.exists():
        return None
    try:
        txt = env_path.read_text(encoding="utf-8")
    except Exception:
        return None
    for line in txt.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, val = s.split("=", 1)
        if k.strip() == key:
            return val.strip().strip("\"").strip("'")
    return None


def cmd_paper(ns: argparse.Namespace) -> int:
    client_id = ns.client_id or _env_get("CLIENT_ID") or _env_get("DHAN_CLIENT_ID")
    token = ns.access_token or _env_get("ACCESS_TOKEN") or _env_get("DHAN_ACCESS_TOKEN")
    if not client_id or not token:
        print("error: provide --client-id/--access-token or set in src/.env or env vars", file=sys.stderr)
        return 2

    dhan = DhanProvider(client_id=client_id, access_token=token)
    rows = run_dhan_paper(
        dhan=dhan,
        capital_inr=float(ns.capital_inr),
        start=ns.start,
        end=ns.end,
        premium_sl_pct=float(ns.premium_sl_pct),
        moneyness=ns.moneyness,
    )

    out = [
        {
            "day": r.day.isoformat(),
            "direction": r.direction,
            "option_security_id": r.option_security_id,
            "qty": r.qty,
            "entry_ts": r.entry_ts.isoformat(),
            "entry_price": r.entry_price,
            "exit_ts": r.exit_ts.isoformat(),
            "exit_price": r.exit_price,
            "outcome": r.outcome,
            "pnl_inr": r.pnl_inr,
        }
        for r in rows
    ]
    ns.output.write_text(json.dumps(out, indent=2), encoding="utf-8")
    total = sum(r["pnl_inr"] for r in out) if out else 0.0
    print(f"Wrote {ns.output} ({len(out)} trades). Total pnl_inr={total:.2f}")
    return 0


def cmd_agent(ns: argparse.Namespace) -> int:
    from stock_market.providers.csv_provider import CsvMarketDataProvider
    from stock_market.agent import TradingAgent
    import pandas as pd

    target_date = pd.Timestamp(ns.date).tz_localize("Asia/Kolkata")
    
    n_prov = CsvMarketDataProvider(ns.nifty_csv)
    b_prov = CsvMarketDataProvider(ns.bank_csv)
    
    # Load data for that specific day
    df_n = n_prov.load_ohlcv_5m("NIFTY", start=target_date, end=target_date + pd.Timedelta(days=1))
    df_b = b_prov.load_ohlcv_5m("BANKNIFTY", start=target_date, end=target_date + pd.Timedelta(days=1))
    
    vix_level = None
    if ns.vix_csv:
        v_prov = CsvMarketDataProvider(ns.vix_csv)
        df_v = v_prov.load_ohlcv_5m("VIX", start=target_date, end=target_date + pd.Timedelta(days=1))
        if not df_v.empty:
            # Get 2:55 PM VIX
            vix_row = df_v[df_v.index.hour == 14]
            vix_row = vix_row[vix_row.index.minute == 55]
            if not vix_row.empty:
                vix_level = float(vix_row["close"].iloc[0])

    agent = TradingAgent()
    decision = agent.decide(df_n, df_b, vix_level)
    
    print("\n" + "="*40)
    print(f" AGENT DECISION FOR {ns.date}")
    print("="*40)
    print(f"GRADE: {decision.grade.value}")
    print("\nREASONING:")
    for r in decision.reasoning:
        print(f" - {r}")
    
    if decision.strategy_params:
        print("\nRECOMMENDED STRATEGY PARAMS:")
        for k, v in decision.strategy_params.items():
            print(f" --{k.replace('_', '-')}: {v}")
    
    print("="*40 + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    return int(ns.func(ns))


if __name__ == "__main__":
    raise SystemExit(main())
