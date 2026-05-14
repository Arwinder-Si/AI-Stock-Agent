
import os
import requests
import pyotp
import sys

def get_fresh_token():
    client_id = os.getenv("DHAN_CLIENT_ID")
    pin = os.getenv("DHAN_PIN")
    totp_secret = os.getenv("DHAN_TOTP_SECRET")

    if not all([client_id, pin, totp_secret]):
        print("Error: Missing credentials (DHAN_CLIENT_ID, DHAN_PIN, or DHAN_TOTP_SECRET)")
        sys.exit(1)

    # 1. Generate TOTP code
    totp = pyotp.TOTP(totp_secret.replace(" ", ""))
    current_otp = totp.now()

    # 2. Call Dhan Auth API
    url = f"https://auth.dhan.co/app/generateAccessToken?dhanClientId={client_id}&pin={pin}&totp={current_otp}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    }
    
    print(f"Requesting fresh access token for Client ID ending in ...{client_id[-4:]}")
    print(f"Generated TOTP: {current_otp}")
    
    response = requests.post(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("accessToken")
        if token:
            print("Successfully generated fresh Access Token.")
            # Print for GitHub Action to capture (Masked in logs if possible)
            # Actually, we will write it to a temporary file for the next step
            with open("dhan_token.txt", "w") as f:
                f.write(token)
            return token
        else:
            print(f"Error: Token not found in response. Response: {data}")
    else:
        print(f"Error: Auth API failed with status {response.status_code}")
        print(f"Details: {response.text}")
    
    sys.exit(1)

if __name__ == "__main__":
    get_fresh_token()
