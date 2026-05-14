import os
import sys

# Add src folder to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from stock_market.auth_manager import get_fresh_token

# IMPORTANT NEW IMPORTS
from dhanhq import DhanContext, dhanhq


def test_dhan_connection():
    print("Testing Dhan Connectivity...")

    try:
        # Generate fresh token
        token = get_fresh_token()

        # Get client ID
        client_id = os.getenv("DHAN_CLIENT_ID")

        if not client_id:
            raise Exception("DHAN_CLIENT_ID not found")

        print(f"Using Client ID ending in ...{client_id[-4:]}")

        # Create DhanContext (required in v2.2.0)
        dhan_context = DhanContext(
            client_id=str(client_id),
            access_token=str(token)
        )

        print("DhanContext created successfully.")

        # Initialize API client
        dhan = dhanhq(dhan_context)

        print("Dhan client initialized successfully.")

        # Test API call
        response = dhan.get_fund_limits()

        print("\nAPI Response:")
        print(response)

        print("\n[SUCCESS] Connected to Dhan successfully!")

    except Exception as e:
        print(f"\n[ERROR] Connection Test Failed: {e}")


if __name__ == "__main__":
    test_dhan_connection()