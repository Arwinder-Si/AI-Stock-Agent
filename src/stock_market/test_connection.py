
import os
import sys
from stock_market.auth_manager import get_fresh_token
from dhanhq import dhanhq

def test_dhan_connection():
    print("Testing Dhan Connectivity...")
    try:
        # 1. Test Automated Login (TOTP + Pin)
        token = get_fresh_token()
        client_id = os.getenv("DHAN_CLIENT_ID")
        
        # 2. Test API Access
        from dhanhq import dhanhq
        try:
            dhan = dhanhq(token)
            profile = dhan.get_fund_limits()
            if profile.get('status') == 'success':
                print(f"\n[SUCCESS] Connected to Dhan successfully!")
                print(f"Fund Limits Status: {profile.get('status')}")
                print("Your Automated Login system is working perfectly!")
            else:
                print(f"\n[FAILURE] Connected but could not fetch funds: {profile}")
        except Exception as e:
            print(f"\n[ERROR] Connection failed: {str(e)}")

        if dhan and profile.get('status') == 'success':
            name = profile.get('data', {}).get('clientName', 'Unknown')
            print(f"\n[SUCCESS] Connected to Dhan as: {name}")
            print("Your Automated Login system is working perfectly!")
        else:
            print(f"\n[FAILURE] Could not find a working connection signature.")
            print(f"Last profile response: {profile if 'profile' in locals() else 'None'}")
            
    except Exception as e:
        print(f"\n[ERROR] Connection Test Failed: {str(e)}")
        print("Check if your Pin or TOTP Secret is correct in GitHub Secrets.")

if __name__ == "__main__":
    # Add src to path for imports
    sys.path.append(os.path.join(os.getcwd(), "src"))
    test_dhan_connection()
