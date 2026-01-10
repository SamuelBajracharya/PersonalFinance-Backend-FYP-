import uuid
from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    total_xp = Column(Integer, default=0)
    savings = Column(Integer, default=0)
    goals_completed = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    bank_accounts = relationship("BankAccount", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    budgets = relationship("Budget", back_populates="user")
    unlocked_rewards = relationship("UserReward", back_populates="user")

    @property
    def rank(self):
        xp = self.total_xp
        if xp < 500:
            return "Rookie Rocket"
        elif xp < 2000:
            return "Bronze Brawler"
        elif xp < 5000:
            return "Silver Surfer"
        elif xp < 8000:
            return "Golden Gladiator"
        elif xp < 10000:
            return "Platinum Pirate"
        elif xp < 15000:
            return "Diamond Dynamo"
        else:
            return "Master of Mischief"
