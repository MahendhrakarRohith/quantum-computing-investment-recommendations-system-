from app.ml.engine import PredictionEngine
from app.ml.sentiment import get_news_sentiment

def generate_report():
    print("🧠 Generating Master Intelligence Report for RELIANCE...")
    
    # 1. Get AI Predictions
    engine = PredictionEngine('data/reliance_history.csv')
    arima_p = engine.get_arima_prediction()
    lstm_p = engine.get_lstm_prediction(epochs=10)
    current = engine.df['close'].iloc[-1]
    
    # 2. Get News Sentiment
    sent_score, sent_label = get_news_sentiment("Reliance Industries")
    
    # 3. Final Logic
    ai_move = "UP" if (arima_p + lstm_p)/2 > current else "DOWN"
    
    print("\n===============================")
    print(f"       RELIANCE REPORT        ")
    print("===============================")
    print(f"Price: ₹{current:.2f}")
    print(f"AI Prediction: {ai_move}")
    print(f"News Sentiment: {sent_label} ({sent_score:.2f})")
    print("-------------------------------")
    
    if ai_move == "UP" and sent_label == "Positive":
        print("✅ FINAL SIGNAL: STRONG BUY (High Confidence)")
    elif ai_move == "UP" or sent_label == "Positive":
        print("🟡 FINAL SIGNAL: WATCH/HOLD (Mixed Signals)")
    else:
        print("🔻 FINAL SIGNAL: AVOID/SELL")
    print("===============================")

if __name__ == "__main__":
    generate_report()