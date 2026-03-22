import pyotp
import pandas as pd
from SmartApi import SmartConnect
from app.core.config import settings
import logging

class AngelOneManager:
    def __init__(self):
        self.smart_api = SmartConnect(api_key=settings.ANGEL_API_KEY)
        self.session = None
        self.feed_token = None
        self.jwt_token = None

    def login(self):
        """Automated login using TOTP"""
        try:
            totp = pyotp.TOTP(settings.ANGEL_TOTP_KEY).now()
            data = self.smart_api.generateSession(
                settings.ANGEL_CLIENT_ID, 
                settings.ANGEL_PASSWORD, 
                totp
            )
            if data['status']:
                self.session = data['data']
                # Persist tokens for downstream websocket usage
                self.feed_token = self.session.get("feedToken")
                self.jwt_token = self.session.get("jwtToken")
                print("Angel One Login Successful")
            else:
                print(f"Login Failed: {data['message']}")
        except Exception as e:
            logging.error(f"Error during login: {e}")

    async def get_historical_data(self, token, symbol, interval="ONE_DAY", days=100):
        """Fetches data and returns a clean Pandas DataFrame"""
        from datetime import datetime, timedelta
        
        to_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M')

        historic_param = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": interval,
            "fromdate": from_date,
            "todate": to_date
        }

        try:
            data = self.smart_api.getCandleData(historic_param)
            if data['status']:
                df = pd.DataFrame(data['data'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
            return None
        except Exception as e:
            logging.error(f"Data Fetch Error: {e}")
            return None

# Singleton instance
angel_client = AngelOneManager()
