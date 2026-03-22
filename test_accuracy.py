import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
import os
import numpy as np
from app.ml.engine import PredictionEngine

# Set a beautiful, professional style for the graph
plt.style.use('dark_background')

def generate_graph(symbol="TCS.NS", test_days=10):
    print(f"📈 Generating AI Accuracy Graph for {symbol} over the last {test_days} days...")
    print("⏳ Please wait. The AI is backtesting day-by-day (this takes about 30-60 seconds)...")

    # 1. Fetch 1 year of historical data
    df = yf.download(tickers=symbol, period="1y", interval="1d", progress=False)
    df = df.reset_index()
    # Flatten columns for compatibility
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
    
    actual_prices = []
    predicted_prices = []
    dates = []

    # 2. Backtesting Loop: Hide future data, predict, then reveal
    total_rows = len(df)
    for i in range(total_rows - test_days, total_rows):
        # Slice data up to the "current" day in the loop
        historical_slice = df.iloc[:i]
        
        # Save slice to a temporary CSV for the Engine to read
        temp_path = f"data/temp_backtest_{symbol}.csv"
        historical_slice.to_csv(temp_path, index=False)
        
        # Run the AI
        try:
            engine = PredictionEngine(temp_path)
            arima_p = engine.get_arima_prediction()
            lstm_p = engine.get_lstm_prediction(epochs=1)
            
            # Ensemble average
            avg_pred = (arima_p + lstm_p) / 2
            
            # The actual price that happened the next day
            actual = float(df['close'].iloc[i])
            date = df['date'].iloc[i].strftime('%Y-%m-%d')
            
            predicted_prices.append(avg_pred)
            actual_prices.append(actual)
            dates.append(date)
            
            print(f"   [{date}] Actual: ₹{actual:.2f} | AI Predicted: ₹{avg_pred:.2f}")
            
        except Exception as e:
            print(f"Error on {date}: {e}")

    # Clean up temp file
    if os.path.exists(temp_path):
        os.remove(temp_path)

    # 3. Calculate Overall Accuracy (MAPE)
    actuals_arr = np.array(actual_prices)
    preds_arr = np.array(predicted_prices)
    mape = np.mean(np.abs((actuals_arr - preds_arr) / actuals_arr)) * 100
    accuracy = 100 - mape

    # 4. DRAW THE GRAPH
    plt.figure(figsize=(12, 6))
    plt.plot(dates, actual_prices, marker='o', color='#10b981', linewidth=2, label='Actual Market Price (Real)')
    plt.plot(dates, predicted_prices, marker='x', color='#3b82f6', linewidth=2, linestyle='dashed', label='AI Predicted Price (LSTM + ARIMA)')
    
    plt.title(f"AI Model Accuracy Validation: {symbol.replace('.NS', '')}\nOverall Model Accuracy: {accuracy:.2f}%", fontsize=14, fontweight='bold', color='white')
    plt.xlabel("Date", fontsize=12, color='#94a3b8')
    plt.ylabel("Price (₹)", fontsize=12, color='#94a3b8')
    plt.xticks(rotation=45, color='#cbd5e1')
    plt.yticks(color='#cbd5e1')
    
    # Add grid and legend
    plt.grid(color='#334155', linestyle='--', linewidth=0.5)
    plt.legend(facecolor='#1e293b', edgecolor='#334155', fontsize=11)
    plt.tight_layout()

    # 5. Save the graph as an image file
    filename = f"AI_Accuracy_Graph_{symbol.replace('.NS', '')}.png"
    plt.savefig(filename, dpi=300, bbox_inches='tight')
    print(f"\n✅ SUCCESS! Graph saved as '{filename}'. Paste this into your presentation!")

if __name__ == "__main__":
    # Ensure matplotlib is installed: pip install matplotlib
    generate_graph("TCS.NS", test_days=10)