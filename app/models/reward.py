import uuid
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLAlchemyEnum
from sqlalchemy.sql import func
from app.db.base import Base
import enum

class RewardType(str, enum.Enum):
    XP = "XP"
    BUDGET_GOALS = "BUDGET_GOALS"
    SAVINGS = "SAVINGS"

class Reward(Base):
    __tablename__ = "rewards"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    tier = Column(Integer, nullable=False)
    reward_type = Column(SQLAlchemyEnum(RewardType), nullable=False)
    requirement_value = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
