import asyncio
import sys
import os

# Adds the current directory to sys.path so it can find 'app'
sys.path.append(os.getcwd())

from app.core.database import engine, Base
# Import models to ensure SQLAlchemy knows about them
from app.models.models import User, UserPreference, Asset, AssetPrice, PortfolioRecommendation, SentimentScore

async def init_models():
    try:
        async with engine.begin() as conn:
            print("Connecting to database...")
            # This creates the .sqlite file and the tables
            await conn.run_sync(Base.metadata.create_all)
        print("Successfully created tables in invest_db.sqlite!")
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(init_models())