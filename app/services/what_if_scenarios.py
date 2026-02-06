from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.bank import Transaction
from app.models.user import User
from app.schemas.what_if_scenarios import WhatIfScenario


from app.crud.bank import get_monthly_spending_history
from app.services.event_logger import log_event_async


def get_what_if_scenarios(db: Session, user: User) -> list[WhatIfScenario]:
    """
    Analyzes a user's current month expenses and generates savings scenarios
    based on reducing spending in their top 5 highest expenditure categories.
    """

    # 1. Aggregate the user's expenses for all time by category (no 30-day filter)
    expenses_by_category = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total_spent"),
        )
        .filter(
            Transaction.user_id == user.user_id,
            Transaction.type == "DEBIT",
            Transaction.category.isnot(None),
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    if not expenses_by_category:
        return []

    # Select the top 5 categories in the last 30 days
    top_5_categories = expenses_by_category[:5]

    # Define smart percentage assignment rules (Category Caps)
    category_percentage_map = {
        # Basic necessities
        "food": 20,
        "groceries": 20,
        "rent": 10,
        "utilities": 10,
        "transport": 30,
        "internet": 30,
        "subscriptions": 50,
        # Discretionary
        "entertainment": 50,
        "dining out": 40,
        "shopping": 50,
    }

    scenarios = []
    for category, total_spent in top_5_categories:
        history = get_monthly_spending_history(db, user.user_id, category)
        months_of_data = 0
        if history["avg_spend"] > 0:
            months_of_data = 1
        if history["avg_spend"] > 0 and history["min_spend"] != history["avg_spend"]:
            months_of_data = 2

        # Get the category-based cap
        category_cap = 40  # Default cap
        for cat_keyword, percentage in category_percentage_map.items():
            if cat_keyword in category.lower():
                category_cap = percentage
                break

        if months_of_data == 1:
            # Only one month of data, use default reduction
            effective_reduction_percentage = min(10, category_cap)
        elif months_of_data >= 2:
            # Use historical reduction logic
            historical_reduction_rate = (
                history["avg_spend"] - history["min_spend"]
            ) / history["avg_spend"]
            if historical_reduction_rate <= 0:
                continue
            effective_reduction_percentage = min(
                historical_reduction_rate * 100, category_cap
            )
        else:
            continue  # No data at all, skip

        monthly_savings = round(
            float(total_spent * effective_reduction_percentage) / 100, 2
        )
        new_budget = round(float(total_spent) - monthly_savings, 2)
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

    # Log the what-if scenario event (non-blocking)
    log_event_async(
        None,
        str(user.user_id),
        "what_if_generated",
        "what_if_scenario",
        str(user.user_id),
        {"scenarios": [s.__dict__ for s in scenarios]},
    )
    return scenarios
