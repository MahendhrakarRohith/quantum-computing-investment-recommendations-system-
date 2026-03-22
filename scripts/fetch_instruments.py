import requests
import pandas as pd
import os

def fetch_instruments():
    # The updated and more stable URL for 2026
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    
    print("📥 Downloading Instrument Master from Angel One...")
    
    try:
        # We add a timeout and headers to prevent the request from hanging
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame(data)
            
            # Filter for NSE Equity (Standard Stocks)
            df = df[df['exch_seg'] == 'NSE']
            
            # Create data folder if not exists
            os.makedirs('data', exist_ok=True)
            
            # Save the file
            df.to_csv('data/instruments.csv', index=False)
            print(f"✅ Success! Saved {len(df)} NSE stocks to data/instruments.csv")
            
            # Verification: Let's check for RELIANCE
            check = df[df['symbol'] == 'RELIANCE-EQ']
            if not check.empty:
                print(f"📌 Verified: RELIANCE Token is {check.iloc[0]['token']}")
        else:
            print(f"❌ Failed! Server returned Status Code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fetch_instruments()