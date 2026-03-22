import pyotp
from SmartApi import SmartConnect
import os
from dotenv import load_dotenv

load_dotenv()

# 1. Generate TOTP
totp_key = os.getenv("ANGEL_TOTP_KEY")
totp = pyotp.TOTP(totp_key).now()
print(f"Generated TOTP: {totp}")

# 2. Connect to Angel One
obj = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
data = obj.generateSession(
    os.getenv("ANGEL_CLIENT_ID"), 
    os.getenv("ANGEL_PASSWORD"), 
    totp
)

if data['status']:
    print("✅ Connection Successful! Your backend can now fetch stock data.")
else:
    print(f"❌ Connection Failed: {data['message']}")