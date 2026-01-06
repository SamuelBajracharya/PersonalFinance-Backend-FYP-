from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.bank import Transaction
from app.models.user import User
from app.schemas.what_if_scenarios import WhatIfScenario

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

    # 3. Select the top 5 categories
    top_5_categories = expenses_by_category[:5]

    # 4. Define smart percentage assignment rules
    category_percentage_map = {
        # Basic necessities: 20%
        "food": 20,
        "groceries": 20,
        "rent": 20,
        "utilities": 20,
        "transport": 30,
        "internet": 30,
        "subscriptions": 30,
        # Discretionary: 40%
        "entertainment": 40,
        "dining out": 40,
        "shopping": 40,
    }

    scenarios = []
    for category, total_spent in top_5_categories:
        # 5. Assign reduction percentage
        reduction_percentage = 40  # Default to 40% for uncategorized
        for cat_keyword, percentage in category_percentage_map.items():
            if cat_keyword in category.lower():
                reduction_percentage = percentage
                break
        
        # 6. Calculate savings
        monthly_savings = round(float(total_spent * reduction_percentage) / 100, 2)
        new_budget = round(float(total_spent) - monthly_savings, 2)

        # 7. Format the message
        message = (
            f"If you cut {reduction_percentage}% from {category} "
            f"you could save Rs{int(monthly_savings)}/month!"
        )

        scenarios.append(
            WhatIfScenario(
                category=category,
                total_spent=round(float(total_spent), 2),
                reduction_percentage=reduction_percentage,
                monthly_savings=monthly_savings,
                new_budget=new_budget,
                message=message,
            )
        )

    return scenarios
