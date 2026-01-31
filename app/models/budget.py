
import uuid
from datetime import datetime, timedelta
from sqlalchemy import (
    Column,
    String,
    Numeric,
    ForeignKey,
    DateTime,
    Date,
    func,
    Boolean,
)
from sqlalchemy.orm import relationship
from app.db.base import Base

def get_default_start_date():
    return datetime.utcnow().date()

def get_default_end_date():
    return (datetime.utcnow() + timedelta(days=30)).date()

class Budget(Base):
    __tablename__ = "budgets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    category = Column(String, nullable=False)
    budget_amount = Column(Numeric(10, 2), nullable=False)
    remaining_budget = Column(Numeric(10, 2), nullable=True)
    start_date = Column(Date, nullable=False, default=get_default_start_date)
    end_date = Column(Date, nullable=False, default=get_default_end_date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_completed = Column(Boolean, nullable=False, default=False)

    user = relationship("User", back_populates="budgets")
