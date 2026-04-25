import sqlite3
import pandas as pd
import time
import asyncio
import os
import yfinance as yf
import json  

from app.ml.engine import PredictionEngine
from app.ml.sentiment import get_news_sentiment

try:
    from app.services.angel_one import angel_client 
except ImportError:
    angel_client = None


def get_dynamic_top_candidates(df_instruments, top_n=50):
    """
    PHASE 1: Dynamic Market Screener
    Instead of hardcoding NIFTY_50, this quickly scans NSE to find 
    the stocks with the highest trading volume and momentum today.
    """
    print(f"🕵️‍♂️ PHASE 1: Scanning the entire NSE for the top {top_n} dynamic candidates...")
    
    # 1. Filter only NSE Equity stocks (Ignore options, futures, etc.)
    nse_equities = df_instruments[(df_instruments['exch_seg'] == 'NSE') & 
                                  (df_instruments['symbol'].str.endswith('-EQ'))]
    
    # 2. Take a safe sample of highly active stocks to avoid API rate limits
    sample_stocks = nse_equities.head(300)['symbol'].tolist()
    
    dynamic_list = []
    yf_symbols = [sym.replace('-EQ', '') + ".NS" for sym in sample_stocks]
    
    print("   Fetching 1-month momentum data...")
    try:
        # Batch download is much faster than looping
        data = yf.download(yf_symbols, period="1mo", group_by="ticker", progress=False)
        
        for sym, yf_sym in zip(sample_stocks, yf_symbols):
            try:
                df_stock = data[yf_sym]
                start_price = float(df_stock['Close'].iloc[0])
                end_price = float(df_stock['Close'].iloc[-1])
                volume = float(df_stock['Volume'].mean())
                
                # Filter: Stock must be > ₹50 and have decent trading volume
                if end_price > 50 and volume > 100000: 
                    momentum_pct = ((end_price - start_price) / start_price) * 100
                    dynamic_list.append({"symbol": sym, "momentum": momentum_pct})
            except Exception:
                continue
                
        # Sort by the highest momentum and pick the Top N
        dynamic_list.sort(key=lambda x: x['momentum'], reverse=True)
        top_dynamic_symbols = [item['symbol'] for item in dynamic_list[:top_n]]
        
        print(f"✅ Phase 1 Complete! Found {len(top_dynamic_symbols)} highly active stocks.")
        return nse_equities[nse_equities['symbol'].isin(top_dynamic_symbols)]
        
    except Exception as e:
        print(f"⚠️ Dynamic scan failed, falling back to safe list. Error: {e}")
        # Fallback list just in case there is no internet connection
        fallback = ["RELIANCE-EQ", "TCS-EQ", "HDFCBANK-EQ", "INFY-EQ", "TATAMOTORS-EQ", "ITC-EQ"]
        return nse_equities[nse_equities['symbol'].isin(fallback)]


def get_macro_trend():
    """Calculates the overall market health using Nifty 50"""
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

    # FIX: Ensure table exists so the script doesn't crash on the first run
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            symbol TEXT UNIQUE,
            current_price REAL,
            target_price REAL,
            upside REAL,
            sentiment TEXT,
            reason TEXT,
            last_updated TIMESTAMP
        )
    ''')
    conn.commit()

    # Load Angel One Instruments
    try:
        df_inv = pd.read_csv('data/instruments.csv')
    except FileNotFoundError:
        print("⚠️ Warning: data/instruments.csv not found. Please ensure Angel One data is downloaded.")
        return

    # Call our new Phase 1 Dynamic Screener!
    nse_stocks = get_dynamic_top_candidates(df_inv, top_n=50) 

    print("🌍 Calculating Macroeconomic Environment (Nifty 50 Trend)...")
    macro_momentum = get_macro_trend()
    macro_multiplier = 1.0 + (macro_momentum * 0.5)

    if angel_client:
        try:
            angel_client.login()
        except Exception as e:
            print(f"⚠️ Angel Login failed: {e}")

    print("\n🚀 Starting PHASE 2: Multi-Factor ML & AI Analysis...")

    # This list collects data to send to the HTML Dashboard
    html_export_data = [] 

    for index, row in nse_stocks.iterrows():
        symbol = row['symbol']
        token = str(row['token'])
        
        try:
            print(f"🔍 Analyzing {symbol}...")
            time.sleep(4) # Prevent API rate limiting
            
            temp_path = f"data/{symbol}_history.csv"
            
            if angel_client:
                hist_df = await angel_client.get_historical_data(token, symbol, "ONE_DAY", 365)
                if hist_df is None or hist_df.empty:
                    continue
                hist_df.to_csv(temp_path, index=False)
            elif not os.path.exists(temp_path):
                continue

            # --- MACHINE LEARNING PREDICTIONS ---
            engine = PredictionEngine(temp_path)
            arima_p = engine.get_arima_prediction()
            lstm_p = engine.get_lstm_prediction(epochs=1) 
            current = engine.df['close'].iloc[-1]
            
            if current < 50:
                continue
                
            base_target_1d = (arima_p + lstm_p) / 2
            
            # --- FUNDAMENTALS ---
            yf_symbol = symbol.replace('-EQ', '') + ".NS"
            fundamental_multiplier = 1.0
            try:
                pe_ratio = yf.Ticker(yf_symbol).info.get('trailingPE', 0)
                if 0 < pe_ratio < 20: fundamental_multiplier = 1.02
                elif pe_ratio > 80: fundamental_multiplier = 0.98
            except:
                pass

            # --- AI SENTIMENT ---
            sent_score, sent_label = get_news_sentiment(symbol)
            sentiment_multiplier = 1.0 + (sent_score * 0.01)
            
            # --- FINAL CALCULATIONS ---
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
            
            # Update SQLite Database
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

            # Add to HTML Export List for the Dashboard
            html_export_data.append({
                "name": symbol.replace('-EQ', ''), # Clean the name for the UI
                "price": current,
                "upside": upside_1w
            })

        except Exception as e:
            print(f"Failed to process {symbol}: {e}")
            continue

    print("✅ Local Database Update Complete!")
    cursor.close()
    conn.close()

    # --- EXPORT DATA FOR THE HTML DASHBOARD ---
    print("📊 Generating data for Smart Wealth Advisor Dashboard...")
    
    # Sort the stocks to find the Top 5 highest predicted returns
    html_export_data.sort(key=lambda x: x['upside'], reverse=True)
    top_stocks = html_export_data[:5]

    # Create the dictionary for the JS file
    frontend_data = {
        "top_stocks": top_stocks,
        "gold_price": 6500, # Hardcoded baseline for Gold
        "fd_rate": {"bank": "SBI Senior Citizen FD", "rate": 7.5}
    }

    # Write it to market_data.js
    with open("market_data.js", "w") as f:
        f.write(f"const marketData = {json.dumps(frontend_data)};")
    
    print("✅ Web data successfully exported to market_data.js!")
    print("🌐 You can now open index.html to view the final Action Plans.")

if __name__ == "__main__":
    asyncio.run(scan_all_stocks())