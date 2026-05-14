
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import pandas as pd
from typing import Any
from stock_market.strategy_3pm_breakout import BreakoutConfig, evaluate_day, find_reference_candle

class ConfidenceGrade(Enum):
    GRADE_A = "A (Super Scalper - High Conviction)"
    GRADE_B = "B (Pro Scalper - Medium Conviction)"
    NO_TRADE = "No Trade (Low Conviction/High Risk)"

@dataclass
class AgentDecision:
    grade: ConfidenceGrade
    strategy_params: dict[str, Any]
    reasoning: list[str]
    nifty_context: dict[str, Any]
    bank_nifty_context: dict[str, Any]

class TradingAgent:
    def __init__(self, vix_threshold_low: float = 11.0, vix_threshold_high: float = 20.0):
        self.vix_threshold_low = vix_threshold_low
        self.vix_threshold_high = vix_threshold_high

    def decide(
        self, 
        df_nifty: pd.DataFrame, 
        df_bank: pd.DataFrame, 
        vix_level: float | None = None
    ) -> AgentDecision:
        reasons = []
        
        # 1. Evaluate Nifty Context
        n_cfg = BreakoutConfig()
        setup_n, reasons_n = evaluate_day(df_nifty, n_cfg)
        
        # 2. Evaluate Bank Nifty Context
        setup_b, reasons_b = evaluate_day(df_bank, n_cfg)
        
        n_context = self._get_context(df_nifty)
        b_context = self._get_context(df_bank)
        
        # --- DECISION LOGIC ---
        
        # Rule 1: VIX Check
        if vix_level:
            if vix_level < self.vix_threshold_low:
                return AgentDecision(ConfidenceGrade.NO_TRADE, {}, ["VIX too low (no momentum)"], n_context, b_context)
            if vix_level > self.vix_threshold_high:
                return AgentDecision(ConfidenceGrade.NO_TRADE, {}, ["VIX too high (excessive noise/whipsaws)"], n_context, b_context)
            if 13.0 <= vix_level <= 16.0:
                reasons.append("VIX is in the 'Sweet Spot' (13-16)")

        # Rule 2: Index Confluence
        if setup_n and setup_b:
            if setup_n.direction != setup_b.direction:
                return AgentDecision(ConfidenceGrade.NO_TRADE, {}, ["Indices Diverging (Nifty vs Bank Nifty disagreement)"], n_context, b_context)
            reasons.append(f"Dual Index Confluence: Both {setup_n.direction.value}")
        else:
            if not setup_n:
                return AgentDecision(ConfidenceGrade.NO_TRADE, {}, ["Nifty failed setup filters"], n_context, b_context)
            reasons.append("Bank Nifty not participating, trading Nifty only.")

        # Rule 3: ORB Confluence (The Grade A trigger)
        is_orb_break = False
        if setup_n:
            c = setup_n.signal_close
            if setup_n.direction.value == "long" and c > n_context["orb_high"]:
                is_orb_break = True
            elif setup_n.direction.value == "short" and c < n_context["orb_low"]:
                is_orb_break = True
        
        if is_orb_break:
            reasons.append("ORB Breakout confirmed (High Probability)")
            params = {
                "require_orb": True,
                "vol_accel": 1.2,
                "trail_reversal": True,
                "reward_r": 1.5,
                "exit_time": "15:15"
            }
            return AgentDecision(ConfidenceGrade.GRADE_A, params, reasons, n_context, b_context)
        
        # Rule 4: Trend Alignment (The Grade B trigger)
        if setup_n and abs(n_context["trend_pct"]) > 0.3:
            reasons.append(f"Strong Day Trend detected ({n_context['trend_pct']:.2f}%)")
            params = {
                "require_trend_align": True,
                "max_dist_extreme_pct": 0.25,
                "trail_reversal": True,
                "reward_r": 1.2,
                "exit_time": "15:15"
            }
            return AgentDecision(ConfidenceGrade.GRADE_B, params, reasons, n_context, b_context)

        return AgentDecision(ConfidenceGrade.NO_TRADE, {}, ["No high-conviction triggers found"], n_context, b_context)

    def _get_context(self, df: pd.DataFrame) -> dict[str, Any]:
        df = df.sort_index()
        idx_ist = df.index.tz_convert("Asia/Kolkata")
        df_ist = df.copy()
        df_ist.index = idx_ist
        
        # ORB
        orb_bars = df_ist[(df_ist.index.hour == 9) & (df_ist.index.minute >= 15) & (df_ist.index.minute <= 40)]
        orb_h = orb_bars["high"].max() if not orb_bars.empty else 0
        orb_l = orb_bars["low"].min() if not orb_bars.empty else 1e9
        
        # Session
        pre_3pm = df_ist[df_ist.index.hour < 14] # simplified
        day_h = df_ist["high"].max()
        day_l = df_ist["low"].min()
        session_open = df_ist["open"].iloc[0]
        last_price = df_ist["close"].iloc[-1]
        
        return {
            "orb_high": orb_h,
            "orb_low": orb_l,
            "day_high": day_h,
            "day_low": day_l,
            "trend_pct": (last_price - session_open) / session_open * 100.0,
            "last_price": last_price
        }
