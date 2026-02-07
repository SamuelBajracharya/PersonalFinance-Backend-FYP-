import uuid
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db.base import Base


class UserXpMilestone(Base):
    __tablename__ = "user_xp_milestones"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    milestone = Column(Integer, nullable=False)
    achieved_at = Column(DateTime(timezone=True), server_default=func.now())
