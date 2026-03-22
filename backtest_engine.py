import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
from app.ml.engine import PredictionEngine
import warnings
warnings.filterwarnings('ignore')

def get_top_stocks():
    conn = sqlite3.connect('market_leaderboard.db')
    cursor = conn.cursor()
    cursor.execute('SELECT symbol FROM recommendations ORDER BY upside DESC LIMIT 5')
    stocks = [row[0] for row in cursor.fetchall()]
    conn.close()
    return stocks

def run_backtest(test_days=30):
    stocks = get_top_stocks()
    if not stocks:
        print("❌ No stocks found in database. Run background_scanner.py first.")
        return

    print("\n" + "="*60)
    print(f"🧪 INITIATING ALGORITHMIC BACKTEST (Past {test_days} Days)")
    print("="*60)

    total_hit_ratio = []
    total_mape = []

    for symbol in stocks:
        print(f"\n⏳ Backtesting {symbol}...")
        yf_symbol = symbol.replace('-EQ', '.NS')
        
        # Download 1 year of data
        data = yf.download(yf_symbol, period="1y", interval="1d", progress=False)
        if data.empty:
            continue
            
        data = data.reset_index()
        data.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in data.columns]
        
        hits = 0
        misses = 0
        errors = []

        # Loop through the last 30 days
        total_rows = len(data)
        for i in range(total_rows - test_days, total_rows - 1):
            # Hide the future!
            historical_slice = data.iloc[:i]
            temp_path = f"data/temp_backtest.csv"
            historical_slice.to_csv(temp_path, index=False)
            
            try:
                # Ask AI to predict tomorrow
                engine = PredictionEngine(temp_path)
                arima_p = engine.get_arima_prediction()
                lstm_p = engine.get_lstm_prediction()
                ai_prediction = (arima_p + lstm_p) / 2
                
                # What actually happened tomorrow?
                current_price = float(data['close'].iloc[i-1])
                actual_next_price = float(data['close'].iloc[i])
                
                # Did it guess the trend correctly? (Directional Accuracy)
                ai_trend = "UP" if ai_prediction > current_price else "DOWN"
                actual_trend = "UP" if actual_next_price > current_price else "DOWN"
                
                if ai_trend == actual_trend:
                    hits += 1
                else:
                    misses += 1
                    
                # Calculate the exact mathematical error
                error = abs((actual_next_price - ai_prediction) / actual_next_price) * 100
                errors.append(error)
                
            except Exception as e:
                print(f"   ⚠️ Skipped a day due to AI error: {e}")

        # Calculate metrics for this specific stock
        if hits + misses > 0:
            stock_hit_ratio = (hits / (hits + misses)) * 100
            stock_mape = np.mean(errors)
            
            total_hit_ratio.append(stock_hit_ratio)
            total_mape.append(stock_mape)
            
            print(f"   🎯 Directional Hit Ratio: {stock_hit_ratio:.1f}%")
            print(f"   📉 Margin of Error (MAPE): {stock_mape:.2f}%")

    # Final System Report
    print("\n" + "="*60)
    print("🏆 FINAL SYSTEM ACCURACY REPORT")
    print("="*60)
    print(f"Overall AI Hit Ratio:      {np.mean(total_hit_ratio):.2f}%")
    print(f"Average System Error Rate: {np.mean(total_mape):.2f}%")
    print(f"Overall System Accuracy:   {100 - np.mean(total_mape):.2f}%")
    print("="*60)

if __name__ == "__main__":
    run_backtest()