import pandas as pd
from SmartApi import SmartConnect
import pyotp
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

def get_history():
    # 1. Setup Session
    api_key = os.getenv("ANGEL_API_KEY")
    totp_key = os.getenv("ANGEL_TOTP_KEY").strip().replace(" ", "")
    totp = pyotp.TOTP(totp_key).now()
    
    smart_api = SmartConnect(api_key=api_key)
    session = smart_api.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)

    if not session['status']:
        print(f"❌ Login Failed: {session['message']}")
        return

    # 2. Define Parameters for RELIANCE (Token 2885)
    # We will fetch 1 year of daily data
    params = {
        "exchange": "NSE",
        "symboltoken": "2885",
        "interval": "ONE_DAY",
        "fromdate": (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d 09:15'),
        "todate": datetime.now().strftime('%Y-%m-%d 15:30')
    }

    print("📊 Fetching 1 year of daily history for RELIANCE...")
    data = smart_api.getCandleData(params)

    if data['status']:
        # Convert raw API response to a clean DataFrame
        # Column order from Angel One: [Timestamp, Open, High, Low, Close, Volume]
        df = pd.DataFrame(data['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Save to CSV for the AI Model
        os.makedirs('data', exist_ok=True)
        df.to_csv('data/reliance_history.csv', index=False)
        print("✅ Success! Created data/reliance_history.csv")
        print(f"Total records fetched: {len(df)}")
    else:
        print(f"❌ API Error: {data['message']}")

if __name__ == "__main__":
    get_history()