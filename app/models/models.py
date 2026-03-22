from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import List, Optional
from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    preferences: Mapped["UserPreference"] = relationship("UserPreference", back_populates="user", uselist=False)
    recommendations: Mapped[List["PortfolioRecommendation"]] = relationship("PortfolioRecommendation", back_populates="user")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    risk_level: Mapped[str] = mapped_column(String)  # Low, Medium, High
    investment_amount: Mapped[float] = mapped_column(Float)
    duration_months: Mapped[int] = mapped_column(Integer)
    asset_types: Mapped[dict] = mapped_column(JSON)  # e.g. {"types": ["stocks", "etfs"]}

    user: Mapped["User"] = relationship("User", back_populates="preferences")

class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    asset_class: Mapped[str] = mapped_column(String) # Equity, Crypto, ETF

    prices: Mapped[List["AssetPrice"]] = relationship("AssetPrice", back_populates="asset")
    sentiment: Mapped["SentimentScore"] = relationship("SentimentScore", back_populates="asset")

class AssetPrice(Base):
    __tablename__ = "asset_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    close_price: Mapped[float] = mapped_column(Float)
    
    asset: Mapped["Asset"] = relationship("Asset", back_populates="prices")

class PortfolioRecommendation(Base):
    __tablename__ = "portfolio_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    allocation_data: Mapped[dict] = mapped_column(JSON) # e.g. {"AAPL": 0.4, "TSLA": 0.6}
    expected_return: Mapped[float] = mapped_column(Float)
    optimization_type: Mapped[str] = mapped_column(String) # Classical vs Quantum
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="recommendations")

class SentimentScore(Base):
    __tablename__ = "sentiment_scores"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    score: Mapped[float] = mapped_column(Float) # -1 to 1
    label: Mapped[str] = mapped_column(String) # Positive, Neutral, Negative
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    asset: Mapped["Asset"] = relationship("Asset", back_populates="sentiment")