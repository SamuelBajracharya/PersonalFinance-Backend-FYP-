import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base

class UserReward(Base):
    __tablename__ = "user_rewards"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    reward_id = Column(String, ForeignKey("rewards.id"), nullable=False)
    unlocked_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="unlocked_rewards")
    reward = relationship("Reward")

    __table_args__ = (UniqueConstraint('user_id', 'reward_id', name='_user_reward_uc'),)
