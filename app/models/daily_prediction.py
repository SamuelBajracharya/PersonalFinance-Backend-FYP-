import uuid
from sqlalchemy import (
    Column,
    String,
    Numeric,
    ForeignKey,
    DateTime,
    Date,
    func,
    Integer,
)
from sqlalchemy.orm import relationship
from app.db.base import Base

class DailyPrediction(Base):
    __tablename__ = "daily_predictions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    prediction_date = Column(Date, nullable=False)
    category = Column(String, nullable=False)
    day_of_week = Column(String, nullable=False)
    day_of_week_id = Column(Integer, nullable=False)
    rolling_7_day_avg = Column(Numeric(10, 2), nullable=False)
    budget_remaining = Column(Numeric(10, 2), nullable=False)
    predicted_amount = Column(Numeric(10, 2), nullable=False)
    risk_probability = Column(Numeric(10, 4), nullable=False)
    risk_level = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="predictions")
