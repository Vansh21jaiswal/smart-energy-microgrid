import getpass
import requests
import urllib.parse

print("Zoho OAuth Token Exchange")
client_id = input("Enter your Self Client ID: ").strip()
client_secret = getpass.getpass("Enter your Self Client Secret: ").strip()
code = getpass.getpass("Paste your generated code: ").strip()

url = "https://accounts.zoho.in/oauth/v2/token"
params = {
    "grant_type": "authorization_code",
    "client_id": client_id,
    "client_secret": client_secret,
    "code": code,
}

try:
    response = requests.post(url, params=params, timeout=20)
    result = response.json()

    if response.ok and "access_token" in result:
        print("\nAccess token received successfully!")
        print("Token type:", result.get("token_type", "Zoho-oauthtoken"))
        print("Expires in seconds:", result.get("expires_in", "not specified"))
        print("\nSave the token securely; do not share it.")
        with open(".zoho_access_token", "w") as f:
            f.write(result["access_token"])
        print("Saved to .zoho_access_token in this folder.")
    else:
        print("\nToken exchange failed.")
        print("Zoho response:", {
            k: v for k, v in result.items()
            if k not in ("access_token", "refresh_token", "client_secret")
        })
except requests.RequestException as e:
    print("Request failed:", type(e).__name__)
