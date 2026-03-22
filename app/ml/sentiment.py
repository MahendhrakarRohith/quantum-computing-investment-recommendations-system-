import requests
from textblob import TextBlob
import os
from dotenv import load_dotenv

load_dotenv()

def get_news_sentiment(ticker_name="Reliance Industries"):
    api_key = os.getenv("NEWS_API_KEY")
    url = f"https://newsapi.org/v2/everything?q={ticker_name}&apiKey={api_key}&language=en&pageSize=5"
    
    try:
        response = requests.get(url)
        articles = response.json().get('articles', [])
        
        if not articles:
            return 0.0, "Neutral"

        scores = []
        for art in articles:
            text = f"{art['title']} {art['description']}"
            analysis = TextBlob(text)
            scores.append(analysis.sentiment.polarity) # Ranges from -1 (Neg) to 1 (Pos)
        
        avg_score = sum(scores) / len(scores)
        label = "Positive" if avg_score > 0.1 else "Negative" if avg_score < -0.1 else "Neutral"
        
        return avg_score, label
    except Exception as e:
        print(f"News Error: {e}")
        return 0.0, "Error"