from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.bank import Transaction
from app.models.user import User
from app.schemas.what_if_scenarios import WhatIfScenario

from app.crud.bank import get_monthly_spending_history


def get_what_if_scenarios(db: Session, user: User) -> list[WhatIfScenario]:
    """
    Analyzes a user's current month expenses and generates savings scenarios
    based on reducing spending in their top 5 highest expenditure categories.
    """
    
    # 1. Get the start and end of the current month
    today = datetime.utcnow().date()
    start_of_month = today.replace(day=1)
    
    # 2. Aggregate the user's expenses for the current month by category
    expenses_by_category = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total_spent"),
        )
        .filter(
            Transaction.user_id == user.user_id,
            Transaction.date >= start_of_month,
            Transaction.type == "DEBIT",
            Transaction.category.isnot(None)
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    if not expenses_by_category:
        return []

    # Select the top 5 categories
    top_5_categories = expenses_by_category[:5]

    # Define smart percentage assignment rules (Category Caps)
    category_percentage_map = {
        # Basic necessities
        "food": 20, "groceries": 20, "rent": 10, "utilities": 10,
        "transport": 30, "internet": 30, "subscriptions": 50,
        # Discretionary
        "entertainment": 50, "dining out": 40, "shopping": 50,
    }

    scenarios = []
    for category, total_spent in top_5_categories:
        # Use historical spending to determine a realistic reduction rate.
        history = get_monthly_spending_history(db, user.user_id, category)
        historical_reduction_rate = 0
        if history["avg_spend"] > 0:
            historical_reduction_rate = (history["avg_spend"] - history["min_spend"]) / history["avg_spend"]

        # If user's spending is already at its minimum, don't suggest a cut.
        if historical_reduction_rate <= 0:
            continue

        # Get the category-based cap
        category_cap = 40  # Default cap
        for cat_keyword, percentage in category_percentage_map.items():
            if cat_keyword in category.lower():
                category_cap = percentage
                break
        
        # The final percentage is capped by the lower of the historical rate and the category cap.
        effective_reduction_percentage = min(historical_reduction_rate * 100, category_cap)
        

        # Calculate savings based on the effective rate
        monthly_savings = round(float(total_spent * effective_reduction_percentage) / 100, 2)
        new_budget = round(float(total_spent) - monthly_savings, 2)

        # Format the message
        message = (
            f"If you cut {int(effective_reduction_percentage)}% from {category} "
            f"you could save Rs{int(monthly_savings)}/month!"
        )

        scenarios.append(
            WhatIfScenario(
                category=category,
                total_spent=round(float(total_spent), 2),
                reduction_percentage=int(effective_reduction_percentage),
                monthly_savings=monthly_savings,
                new_budget=new_budget,
                message=message,
            )
        )

    return scenarios

