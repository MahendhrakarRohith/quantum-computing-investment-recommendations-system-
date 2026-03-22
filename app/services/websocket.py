# app/services/websocket.py
import asyncio
import json
import os
import pyotp
import logging
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from app.core.config import settings

# Suppress overly verbose Angel One logs
logging.getLogger("websocket").setLevel(logging.WARNING)

class AngelOneWebSocket:
    def __init__(self, connection_manager):
        self.manager = connection_manager
        
        self.api_key = os.getenv('ANGEL_API_KEY')
        self.client_code = os.getenv('ANGEL_CLIENT_ID')
        self.pin = os.getenv('ANGEL_PASSWORD')
        self.totp_secret = os.getenv('ANGEL_TOTP_KEY')
        
        self.feed_token = None
        self.sws = None
        self.is_connected = False
        
        # We need a dictionary to translate NSE Tokens to readable Tickers
        # (e.g., Angel One sends "2885", we translate to "RELIANCE")
        self.token_map = {
            "2885": "RELIANCE",
            "11536": "TCS",
            "1333": "HDFCBANK",
            "1594": "INFY",
            "4339": "SBI"
        }

    def _perform_auto_login(self):
        try:
            print("🔐 Initiating Angel One Auto-Login sequence...")
            smartApi = SmartConnect(api_key=self.api_key)
            live_totp = pyotp.TOTP(self.totp_secret).now()
            
            data = smartApi.generateSession(self.client_code, self.pin, live_totp)
            
            if data['status']:
                self.feed_token = smartApi.getfeedToken()
                print("✅ Auto-Login Successful! Secured daily Feed Token.")
                return True
            else:
                print(f"❌ Auto-Login Rejected: {data['message']}")
                return False
        except Exception as e:
            print(f"🔴 Auto-Login Exception: {e}")
            return False

    def _on_data(self, wsapp, message):
        """This function catches the live ticks from the exchange."""
        try:
            # message is already a decoded dict thanks to SmartWebSocketV2
            token = message.get("token")
            ltp = message.get("last_traded_price")
            
            if token and ltp:
                # Convert price from paise to rupees
                price_in_rupees = ltp / 100.0 
                
                # Look up the ticker symbol
                symbol = self.token_map.get(str(token), f"UNKNOWN_{token}")
                
                tick_data = {
                    "type": "TICK",
                    "symbol": symbol,
                    "ltp": round(price_in_rupees, 2)
                }
                
                # Push the tick to your dashboard
                asyncio.run(self.manager.broadcast(tick_data))
                
        except Exception as e:
            print(f"Tick parsing error: {e}")

    def _on_open(self, wsapp):
        print("🟢 Angel One Live Stream Connected!")
        self.is_connected = True
        
        # Subscribe to the tokens we mapped above
        # Mode 1 = "LTP" (Last Traded Price only, very fast)
        # Exchange 1 = "NSE"
        token_list = [{"exchangeType": 1, "tokens": list(self.token_map.keys())}]
        
        self.sws.subscribe("hello_client", 1, token_list)

    def _on_error(self, wsapp, error):
        print(f"🔴 Angel One Stream Error: {error}")

    def _on_close(self, wsapp):
        print("⭕ Angel One Stream Disconnected.")
        self.is_connected = False

    async def connect_and_stream(self):
        """Main connection manager."""
        if not all([self.api_key, self.client_code, self.pin, self.totp_secret]):
            print("⚠️ Angel One credentials incomplete. Stream disabled.")
            return

        login_success = await asyncio.to_thread(self._perform_auto_login)
        
        if not login_success:
            print("🔀 Login failed. Stream disabled.")
            return

        # Initialize the official SmartAPI WebSocket
        self.sws = SmartWebSocketV2(
            auth_token=self.feed_token,
            api_key=self.api_key,
            client_code=self.client_code,
            feed_token=self.feed_token
        )

        # Wire up our event handlers
        self.sws.on_open = self._on_open
        self.sws.on_data = self._on_data
        self.sws.on_error = self._on_error
        self.sws.on_close = self._on_close

        # Launch the connection in a background thread so it doesn't freeze FastAPI
        print("⏳ Connecting to NSE Live Feed...")
        await asyncio.to_thread(self.sws.connect)

    def stop(self):
        if self.sws:
            self.sws.close_connection()
            self.is_connected = False