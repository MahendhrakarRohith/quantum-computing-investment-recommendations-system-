import requests
from app.core.config import settings
from app.ml.sentiment import analyze_sentiment

class NewsService:
    def __init__(self):
        self.api_key = settings.NEWS_API_KEY
        self.base_url = "https://newsapi.org/v2/everything"

    async def get_sentiment_for_ticker(self, ticker: str):
        """
        Fetches latest news and calculates an average sentiment score.
        """
        params = {
            "q": ticker,
            "apiKey": self.api_key,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 5
        }
        
        try:
            response = requests.get(self.base_url, params=params)
            articles = response.json().get("articles", [])
            
            if not articles:
                return {"score": 0.0, "label": "Neutral", "count": 0}

            total_score = 0
            for art in articles:
                # Combine title and description for better context
                full_text = f"{art.get('title', '')} {art.get('description', '')}"
                result = analyze_sentiment(full_text)
                total_score += result['score']

            avg_score = total_score / len(articles)
            
            # Categorize the average
            if avg_score > 0.1: label = "Positive"
            elif avg_score < -0.1: label = "Negative"
            else: label = "Neutral"

            return {"score": avg_score, "label": label, "count": len(articles)}

        except Exception as e:
            print(f"News API Error: {e}")
            return {"score": 0.0, "label": "Error", "count": 0}

news_service = NewsService()