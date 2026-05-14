
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
        
        # 2. Test API Access (Auto-Discovery Mode)
        dhan = None
        signatures = [
            lambda: dhanhq(client_id, token),
            lambda: dhanhq(token),
            lambda: dhanhq(client_id=client_id, access_token=token)
        ]
        
        for i, sig in enumerate(signatures):
            try:
                print(f" - Attempting connection signature {i+1}...")
                dhan = sig()
                # Verify it actually works by calling a simple method
                profile = dhan.get_profile()
                if profile.get('status') == 'success':
                    break
            except Exception as e:
                print(f"   Signature {i+1} failed: {str(e)}")
                continue

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
