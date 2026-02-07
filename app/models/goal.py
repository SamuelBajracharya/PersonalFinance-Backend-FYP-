import uuid
import enum
from sqlalchemy import (
    Column,
    String,
    Numeric,
    ForeignKey,
    Date,
    DateTime,
    Enum as SQLAlchemyEnum,
    func,
)
from sqlalchemy.orm import relationship
from app.db.base import Base


class GoalType(str, enum.Enum):
    SAVINGS = "SAVINGS"
    EMERGENCY = "EMERGENCY"
    TRAVEL = "TRAVEL"
    DEBT = "DEBT"


class GoalStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    AT_RISK = "AT_RISK"
    ACHIEVED = "ACHIEVED"
    EXPIRED = "EXPIRED"


class Goal(Base):
    __tablename__ = "goals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    goal_type = Column(SQLAlchemyEnum(GoalType), nullable=False)
    target_amount = Column(Numeric(12, 2), nullable=False)
    current_amount = Column(Numeric(12, 2), nullable=False, default=0)
    deadline = Column(Date, nullable=False)
    status = Column(
        SQLAlchemyEnum(GoalStatus), nullable=False, default=GoalStatus.ACTIVE
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="goals")
