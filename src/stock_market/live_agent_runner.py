
import sys
import os
from datetime import datetime
import pandas as pd
import pytz
import time

sys.path.append(os.path.join(os.getcwd(), "src"))

from stock_market.providers.dhan_provider import DhanProvider, DhanInstrument
from stock_market.agent import TradingAgent, ConfidenceGrade

# Dhan Security IDs for Indices
INST_NIFTY = DhanInstrument(security_id="13", exchange_segment="IDX_I", instrument_type="INDEX")
INST_BANKNIFTY = DhanInstrument(security_id="25", exchange_segment="IDX_I", instrument_type="INDEX")
INST_VIX = DhanInstrument(security_id="19", exchange_segment="IDX_I", instrument_type="INDEX")

def run_live_decision(client_id: str, access_token: str):
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")
    
    print(f"[{now.strftime('%H:%M:%S')}] Starting Daily Recap for {today_str}...")
    
    dhan = DhanProvider(client_id, access_token)
    
    try:
        # Fetch Recap (09:15 to Now)
        print(" - Fetching Nifty 50 candles...")
        df_n = dhan.intraday_5m(INST_NIFTY, today_str, today_str)
        
        print(" - Fetching Bank Nifty candles...")
        df_b = dhan.intraday_5m(INST_BANKNIFTY, today_str, today_str)
        
        print(" - Fetching India VIX...")
        df_v = dhan.intraday_5m(INST_VIX, today_str, today_str)
        
        vix_level = df_v['close'].iloc[-1] if not df_v.empty else None
        
        # Initialize Agent
        agent = TradingAgent()
        
        print("\n" + "="*50)
        print(f" AGENT ANALYSIS FOR {now.strftime('%d-%b-%Y %H:%M:%S')}")
        print("="*50)
        
        decision = agent.decide(df_n, df_b, vix_level)
        
        print(f"CONFIDENCE GRADE: {decision.grade.value}")
        if vix_level:
            print(f"CURRENT VIX: {vix_level:.2f}")
            
        print("\nMARKET REASONING:")
        for r in decision.reasoning:
            print(f" [OK] {r}")
            
        if decision.grade != ConfidenceGrade.NO_TRADE:
            print("\n!!! ACTION REQUIRED: TAKE TRADE !!!")
            print("STRATEGY PARAMS:")
            for k, v in decision.strategy_params.items():
                print(f"  --{k}: {v}")
        else:
            print("\n[SKIP] Stay cash today. Protect your capital.")
            
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"CRITICAL ERROR during live recap: {str(e)}")

if __name__ == "__main__":
    # In production, these will be environment variables
    cid = os.getenv("DHAN_CLIENT_ID", "YOUR_CLIENT_ID")
    tok = os.getenv("DHAN_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")
    
    if cid == "YOUR_CLIENT_ID":
        print("Error: Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN env vars.")
    else:
        run_live_decision(cid, tok)
