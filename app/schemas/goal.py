from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
from app.models.goal import GoalType, GoalStatus


class GoalBase(BaseModel):
    goal_type: GoalType
    target_amount: Decimal
    deadline: date


class GoalCreate(GoalBase):
    pass


class Goal(GoalBase):
    id: str
    user_id: str
    current_amount: Decimal
    status: GoalStatus
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class GoalImpactAnalysis(BaseModel):
    goal_id: str
    goal_type: GoalType
    target_amount: Decimal
    current_amount: Decimal
    deadline: date
    status: GoalStatus
    progress_percent: float
    required_monthly_contribution: Decimal
    projected_completion_months: int | None
    is_on_track: bool
    recent_monthly_savings: Decimal
    predicted_monthly_savings: Decimal
    predicted_monthly_spend: Decimal

    class Config:
        from_attributes = True
