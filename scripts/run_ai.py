from app.ml.engine import PredictionEngine
import pandas as pd

def run_forecast():
    print("🤖 AI Brain is analyzing Reliance data...")
    engine = PredictionEngine('data/reliance_history.csv')
    
    # Get Current Price
    current_price = engine.df['close'].iloc[-1]
    
    # Run Models
    arima_pred = engine.get_arima_prediction()
    lstm_pred = engine.get_lstm_prediction(epochs=15) # 15 iterations
    
    print(f"\n--- RELIANCE ANALYSIS ---")
    print(f"Current Price: ₹{current_price:.2f}")
    print(f"ARIMA Forecast (Short-term): ₹{arima_pred:.2f}")
    print(f"LSTM Forecast (Pattern-based): ₹{lstm_pred:.2f}")
    
    # Simple Decision Logic
    avg_pred = (arima_pred + lstm_pred) / 2
    change = ((avg_pred - current_price) / current_price) * 100
    
    print(f"Signal: {'🚀 BULLISH' if avg_pred > current_price else '🔻 BEARISH'}")
    print(f"Expected Change: {change:.2f}%")

if __name__ == "__main__":
    run_forecast()