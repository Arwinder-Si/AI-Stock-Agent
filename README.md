# AI-Stock-Agent: Professional Scalper AI Trading Agent

This repo contains a **mechanical playbook** (docs) and a **Python backtest** for the late-session 3:00–3:10 breakout idea on **NIFTY 5-minute data**. It includes an automated **Decision Agent** that selects the best strategy (Pro Scalper vs Super Scalper) based on market context (VIX, Trend, Confluence).

## Install

```powershell
cd C:\Users\arwin\Desktop\Stock_market
pip install -e .
```

## AI Trading Agent

The system includes a meta-strategy agent that evaluates Nifty, Bank Nifty, and VIX in real-time.

```powershell
python -m stock_market.cli agent --nifty-csv data\nifty_5m.csv --bank-csv data\bank_5m.csv --vix-csv data\vix_5m.csv --date 2026-05-14
```

## Backtest (CSV)

CSV columns: `datetime`, `open`, `high`, `low`, `close`, `volume` (naive timestamps are treated as Asia/Kolkata).

```powershell
python -m stock_market.cli backtest --csv data\sample_nifty_5m.csv --output-dir out
```

Outputs:

- `out/trades.csv` — one row per trade
- `out/skips.json` — per-day skip reasons when no trade
- `out/metrics.json` — win rate, total/average P&L in points

### Useful CLI knobs

- `--require-trend-align` — only trade with the day's trend
- `--require-orb` — only trade if breaking the morning range
- `--trail-reversal` — exit instantly on a 5m candle reversal
- `--max-sl` — cap risk and tighten SL on big bars
- `--exit-time` — HH:MM hard exit for scalpers (e.g. 15:10)

## Data providers

- **`CsvMarketDataProvider`** — local file (used by CLI).
- **`DhanProvider`** — real-time data and paper trading via Dhan HQ.
- **`YFinanceMarketDataProvider`** — live download via `yfinance` (`--provider yfinance`).

## Docs

- [docs/3pm_breakout_playbook.md](docs/3pm_breakout_playbook.md) — full framework + edge cases + reason codes
- [docs/journal_template.md](docs/journal_template.md) — pre/post trade checklist

## TradingView

- **Indicator (labels):** [tradingview/3pm_breakout_nifty.pine](tradingview/3pm_breakout_nifty.pine)
- **Strategy (orders / backtest):** [tradingview/3pm_breakout_nifty_strategy.pine](tradingview/3pm_breakout_nifty_strategy.pine)

## Disclaimer

Educational only. Not financial advice. Options add gap, spread, theta, and IV risk not modeled in the index-point simulator.
