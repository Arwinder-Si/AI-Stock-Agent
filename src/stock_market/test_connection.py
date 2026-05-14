
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
        
        # 2. Test API Access (Deeper Auto-Discovery)
        import dhanhq as d_module
        
        # Possible class names in various versions
        class_candidates = [
            getattr(d_module, 'dhanhq', None),
            getattr(d_module, 'Dhan', None),
            d_module
        ]
        
        dhan = None
        profile = {}

        for cls in class_candidates:
            if cls is None: continue
            
            # Try different ways to initialize this specific class
            sigs = [
                lambda: cls(token),
                lambda: cls(client_id, token),
                lambda: cls(client_id=client_id, access_token=token)
            ]
            
            for sig in sigs:
                try:
                    dhan = sig()
                    profile = dhan.get_profile()
                    if profile.get('status') == 'success':
                        break
                except:
                    continue
            if dhan and profile.get('status') == 'success':
                break

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
