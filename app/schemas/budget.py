
from pydantic import BaseModel, Field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

class BudgetBase(BaseModel):
    category: str
    budget_amount: Decimal
    start_date: date = Field(default_factory=date.today)
    end_date: date = Field(default_factory=lambda: date.today() + timedelta(days=30))

class BudgetCreate(BudgetBase):
    pass

class BudgetUpdate(BaseModel):
    budget_amount: Decimal

class Budget(BudgetBase):
    id: str
    user_id: str
    start_date: date
    end_date: date
    remaining_budget: Optional[Decimal] = None

    class Config:
        from_attributes = True
