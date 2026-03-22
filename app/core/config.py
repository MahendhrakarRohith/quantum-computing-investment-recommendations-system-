import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from typing import Optional

# Allow .env values to override any existing env vars so the active DB URL is consistent
load_dotenv(override=True)

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Investment System"
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
    SECRET_KEY: Optional[str] = os.getenv("SECRET_KEY")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Add these missing fields so the login service can see them
    ANGEL_CLIENT_ID: Optional[str] = os.getenv("ANGEL_CLIENT_ID")
    ANGEL_PASSWORD: Optional[str] = os.getenv("ANGEL_PASSWORD")
    ANGEL_TOTP_KEY: Optional[str] = os.getenv("ANGEL_TOTP_KEY")
    ANGEL_API_KEY: Optional[str] = os.getenv("ANGEL_API_KEY") # This is your X-PrivateKey
    
    NEWS_API_KEY: Optional[str] = os.getenv("NEWS_API_KEY")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
