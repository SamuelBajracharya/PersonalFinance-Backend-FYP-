
from pydantic import BaseModel
from datetime import date
from decimal import Decimal

class BudgetBase(BaseModel):
    category: str
    budget_amount: Decimal

class BudgetCreate(BudgetBase):
    pass

class BudgetUpdate(BaseModel):
    budget_amount: Decimal

class Budget(BudgetBase):
    id: str
    user_id: str
    start_date: date
    end_date: date

    class Config:
        from_attributes = True
