# 3PM breakout — NIFTY playbook (IST)

Mechanical framework for **late-session momentum expansion** on **NIFTY**, with **options execution** notes. The Python backtest in this repo signals on **index5-minute candles** and measures P&L in **index points** (not option premium).

---

## 1. Core idea

Between **15:00 and 15:10 IST**, price often expands after the **14:55–15:00** five-minute candle defines a tight range. The edge is not “calling direction” — it is **waiting**, **filtering context**, and **executing** only when structure confirms.

---

## 2. Session structure (5-minute bars, bar time = open)

| Phase | Bar open time (IST) | Rule |
|--------|----------------------|------|
| Reference | **14:55** | Record `refHigh`, `refLow`, range = `refHigh − refLow`. |
| Watch | **15:00**, **15:05** only | No new trades after the **15:05** bar closes (i.e. no **15:10** open bar). |
| Hard exit | Last managed exit by **15:25** | Flat by end of the **15:20–15:25** bar (backtest uses this window). |

### Entry (confirmation, not wick)

- **Long**: **Close** > `refHigh` (not merely `high` > `refHigh`).
- **Short**: **Close** < `refLow`.

### Stop (choose one mode; match your playbook backtest CLI)

- **Opposite side**: long stop = `refLow`; short stop = `refHigh`.
- **50% reference range**: stop at **midpoint** of the reference candle (`refLow + 0.5 × range`).

### Target

- Default **1.2R–1.5R** (implementation default **1.35R**). Tune with `--reward-r`.

### Slippage (reality)

- Assume **worse fills** than the signal close. Default **0.5** index points via `--slippage`.

---

## 3. “PRO” checklist — trade only if

1. **Reference candle is not tiny** — range ≥ your minimum (CLI: `--min-ref-range`).
2. **Breakout is real** — **close** beyond level; **body** ≥ fraction of candle range (filter: `WEAK_BODY`).
3. **VWAP + EMA alignment** — long: close ≥ VWAP and ≥ EMA20; short: opposite (skip: `VWAP_EMA_NOT_ALIGNED`).
4. **EMA not dead-flat** — slope of EMA20 over lookback ≥ floor (skip: `EMA_FLAT`, `EMA_NA`).
5. **Not chopping around VWAP** — VWAP cross count ≤ max (skip: `VWAP_CHOP`).
6. **Volume participation** — volume ≥ multiple of rolling average (skip: `LOW_VOLUME`).
7. **Not absurdly extended vs VWAP** — `|close−VWAP|/VWAP` ≤ max (skip: `OVEREXTENDED_VWAP`; CLI: `--max-vwap-dev`).
8. **On time** — only **15:00** and **15:05** open bars.
9. **One trade per day** (conservative mode in code).

---

## 4. Skip / edge cases (mapped to reason codes)

| Situation | Handling | Code(s) in backtest |
|-----------|----------|---------------------|
| Wick spike, close back inside | Require **close** beyond level + **body** filter | (implicit) / `WEAK_BODY` |
| Reference candle too small | Skip | `REF_TOO_SMALL` |
| Sideways / EMA flat | Skip | `EMA_FLAT`, `EMA_NA` |
| Oscillating VWAP | Skip | `VWAP_CHOP` |
| Low volume breakout | Skip | `LOW_VOLUME` |
| Overextended vs VWAP | Skip | `OVEREXTENDED_VWAP` |
| Late entry | Only15:00 & 15:05 bars | (window) |
| Expiry / event days | Manual flag or `--strict-expiry` | `EXPIRY_STRICT_SKIP` |
| Conflicting long+short signal | Skip bar | `CONFLICT_DIRECTION` |
| No 14:55 bar in data | Skip day | `NO_REF_CANDLE` |
| No qualifying breakout | Skip | `NO_BREAKOUT` |

**News / RBI / budget / global shock** — not detectable in price-only backtests: **manual** “do not trade” flag in your journal.

---

## 5. NIFTY **options** execution (not simulated in index backtest)

- Prefer **ATM / slight ITM**; avoid far OTM for this short horizon.
- Theta and IV crush matter in the last **30 minutes** — size down if premium is rich.
- Use a **premium stop** (e.g. 15–25% of debit) *in addition* to structure — the Python engine does not model option marks.
- Widen spreads → skip or cut size.

### Small account (₹10k) operating rules (one trade/day)

These rules are designed so you can **survive the learning curve** and still benefit from the “skip bad days” edge.

- **One trade max per day**: if you get stopped, you are done. If no clean setup appears, you skip.
- **Daily risk cap**: set a hard daily loss limit (example: **1–2% of ₹10k = ₹100–₹200**) and do not exceed it.
- **Risk is premium loss, not “points”**: decide your stop in **premium terms** (e.g. 15–25%) *and* keep the structure stop in mind.
- **Do not force a lot size**: if the smallest tradable lot makes your risk cap impossible, you skip. (No “adjusting rules” to fit a trade.)
- **Avoid bad liquidity**: wide spreads, jumpy quotes, or thin OI near close = skip or reduce size.
- **Skip list (strict)**: news/event days, expiry pin-ball near major strikes, very small 14:55 candle, and late/choppy conditions.

---

## 6. What the Python code does *not* model

- Option greeks, bid/ask, liquidity tiers, circuit limits, broker outages.
- Holiday calendar (empty days in CSV simply produce no trade).
- Multiple entries / re-entries after failure (not enabled by default).

---

## 7. Running the backtest

See [README.md](../README.md). Tune thresholds to match how strict you want to be on **VWAP distance**, **chop**, and **EMA slope** — those three dominate skip frequency on real data.
