from pydantic import BaseModel
from datetime import date
from decimal import Decimal

class BudgetPrediction(BaseModel):
    category: str
    predicted_amount: float
    risk_probability: float
    risk_level: str
    remaining_budget: float
    prediction_date: date

    class Config:
        orm_mode = True

class DailyPredictionCreate(BaseModel):
    user_id: str
    prediction_date: date
    category: str
    day_of_week: str
    day_of_week_id: int
    rolling_7_day_avg: Decimal
    budget_remaining: Decimal
    predicted_amount: Decimal
    risk_probability: Decimal
    risk_level: str

    class Config:
        orm_mode = True
