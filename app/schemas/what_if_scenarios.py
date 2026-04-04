from pydantic import BaseModel, Field


class WhatIfPreferences(BaseModel):
    protected_categories: list[str] = Field(default_factory=list)
    protected_category_cap: int = 12
    category_caps: dict[str, int] = Field(default_factory=dict)
    global_min_reduction: int | None = None
    global_max_reduction: int | None = None


class WhatIfScenario(BaseModel):
    category: str
    total_spent: float
    reduction_percentage: int
    monthly_savings: float
    new_budget: float
    message: str

    class Config:
        from_attributes = True
