import sqlite3
import pandas as pd
import time
import asyncio
import os
import yfinance as yf
from app.ml.engine import PredictionEngine
from app.ml.sentiment import get_news_sentiment

try:
    from app.services.angel_one import angel_client 
except ImportError:
    angel_client = None

# 📢 THE 50 PREMIUM STOCKS TO SCAN (NIFTY 50)
NIFTY_50 = [
    "RELIANCE-EQ", "TCS-EQ", "HDFCBANK-EQ", "ICICIBANK-EQ", "INFY-EQ",
    "ITC-EQ", "SBIN-EQ", "BHARTIARTL-EQ", "LT-EQ", "BAJFINANCE-EQ",
    "HINDUNILVR-EQ", "KOTAKBANK-EQ", "TITAN-EQ", "SUNPHARMA-EQ", "TATAMOTORS-EQ",
    "MARUTI-EQ", "NTPC-EQ", "AXISBANK-EQ", "ULTRACEMCO-EQ", "ASIANPAINT-EQ",
    "COALINDIA-EQ", "BAJAJFINSV-EQ", "ONGC-EQ", "ADANIPORTS-EQ", "M&M-EQ",
    "TATASTEEL-EQ", "WIPRO-EQ", "POWERGRID-EQ", "JSWSTEEL-EQ", "HINDALCO-EQ",
    "NESTLEIND-EQ", "HCLTECH-EQ", "TECHM-EQ", "GRASIM-EQ", "SBILIFE-EQ",
    "HDFCLIFE-EQ", "DIVISLAB-EQ", "CIPLA-EQ", "APOLLOHOSP-EQ", "TATACONSUM-EQ",
    "EICHERMOT-EQ", "BAJAJ-AUTO-EQ", "BRITANNIA-EQ", "INDUSINDBK-EQ", "DRREDDY-EQ",
    "BPCL-EQ", "HEROMOTOCO-EQ", "SHRIRAMFIN-EQ", "ADANIENT-EQ", "LTIM-EQ"
]

def get_macro_trend():
    try:
        nifty = yf.download("^NSEI", period="5d", progress=False)
        start_price = float(nifty['Close'].iloc[0])
        end_price = float(nifty['Close'].iloc[-1])
        return (end_price - start_price) / start_price
    except:
        return 0.0

async def scan_all_stocks():
    print("📁 Connecting to local SQLite database...")
    conn = sqlite3.connect('market_leaderboard.db')
    cursor = conn.cursor()

    df_inv = pd.read_csv('data/instruments.csv')
    nse_stocks = df_inv[(df_inv['exch_seg'] == 'NSE') & (df_inv['symbol'].isin(NIFTY_50))]
    
    print("🌍 Calculating Macroeconomic Environment (Nifty 50 Trend)...")
    macro_momentum = get_macro_trend()
    macro_multiplier = 1.0 + (macro_momentum * 0.5)

    if angel_client:
        try:
            angel_client.login()
        except Exception as e:
            print(f"⚠️ Angel Login failed: {e}")

    print("\n🚀 Starting Multi-Factor AI Scanner (Local Engine)...")

    for index, row in nse_stocks.iterrows():
        symbol = row['symbol']
        token = str(row['token'])
        
        try:
            print(f"🔍 Analyzing {symbol}...")
            time.sleep(4)
            
            temp_path = f"data/{symbol}_history.csv"
            
            if angel_client:
                hist_df = await angel_client.get_historical_data(token, symbol, "ONE_DAY", 365)
                if hist_df is None or hist_df.empty:
                    continue
                hist_df.to_csv(temp_path, index=False)
            elif not os.path.exists(temp_path):
                continue

            engine = PredictionEngine(temp_path)
            arima_p = engine.get_arima_prediction()
            lstm_p = engine.get_lstm_prediction(epochs=1) 
            current = engine.df['close'].iloc[-1]
            
            if current < 50:
                continue
                
            base_target_1d = (arima_p + lstm_p) / 2
            
            yf_symbol = symbol.replace('-EQ', '') + ".NS"
            fundamental_multiplier = 1.0
            try:
                pe_ratio = yf.Ticker(yf_symbol).info.get('trailingPE', 0)
                if 0 < pe_ratio < 20: fundamental_multiplier = 1.02
                elif pe_ratio > 80: fundamental_multiplier = 0.98
            except:
                pass

            sent_score, sent_label = get_news_sentiment(symbol)
            sentiment_multiplier = 1.0 + (sent_score * 0.01)
            
            final_target_1d = base_target_1d * fundamental_multiplier * macro_multiplier * sentiment_multiplier
            upside_1d = ((final_target_1d - current) / current) * 100
            
            final_target_1w = current + ((final_target_1d - current) * 3.5)
            upside_1w = ((final_target_1w - current) / current) * 100
            
            stop_loss = current * 0.98
            model_difference = abs(((arima_p - lstm_p) / current) * 100)
            confidence = max(10, min(99, 100 - (model_difference * 5))) 
            
            reason = (
                f"Models indicate {confidence:.1f}% confidence. "
                f"1-Day Target: ₹{final_target_1d:.2f} ({'+' if upside_1d > 0 else ''}{upside_1d:.2f}%). "
                f"1-Week Target: ₹{final_target_1w:.2f} ({'+' if upside_1w > 0 else ''}{upside_1w:.2f}%). "
                f"🛑 Risk Stop-Loss at ₹{stop_loss:.2f}. "
                f"News Sentiment is '{sent_label}'."
            )
            
            # Reverted to SQLite Syntax
            cursor.execute('''
                INSERT INTO recommendations (symbol, current_price, target_price, upside, sentiment, reason, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(symbol) DO UPDATE SET
                    current_price=excluded.current_price,
                    target_price=excluded.target_price,
                    upside=excluded.upside,
                    sentiment=excluded.sentiment,
                    reason=excluded.reason,
                    last_updated=CURRENT_TIMESTAMP
            ''', (symbol, current, final_target_1w, upside_1w, sent_label, reason))
            
            conn.commit()

        except Exception as e:
            print(f"Failed to process {symbol}: {e}")
            continue

    print("✅ Local Database Update Complete!")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    asyncio.run(scan_all_stocks())