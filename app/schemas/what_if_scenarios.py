from pydantic import BaseModel

class WhatIfScenario(BaseModel):
    category: str
    total_spent: float
    reduction_percentage: int
    monthly_savings: float
    new_budget: float
    message: str

    class Config:
        from_attributes = True
