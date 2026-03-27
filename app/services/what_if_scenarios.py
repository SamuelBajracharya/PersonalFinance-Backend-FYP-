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

    # Calculate previous full calendar month
    today = datetime.utcnow().date()
    first_of_this_month = today.replace(day=1)
    last_month_end = first_of_this_month - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    # Aggregate user's expenses by category for the previous full calendar month
    expenses_by_category = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total_spent"),
        )
        .filter(
            Transaction.user_id == user.user_id,
            Transaction.type == "DEBIT",
            Transaction.category.isnot(None),
            Transaction.date >= datetime.combine(last_month_start, datetime.min.time()),
            Transaction.date <= datetime.combine(last_month_end, datetime.max.time()),
        )
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    if not expenses_by_category:
        return []

    # Only include categories that actually have expenses in this period (could be less than 4)
    top_categories = expenses_by_category[:4]

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
    for category, total_spent in top_categories:
        # Only include categories with positive spending
        if not total_spent or float(total_spent) <= 0:
            continue
        # For "food" use 10% reduction, otherwise use category cap or 10% as default
        if "food" in category.lower():
            effective_reduction_percentage = 10
        else:
            # Use category cap if defined, else 10%
            category_cap = 10
            for cat_keyword, percentage in category_percentage_map.items():
                if cat_keyword in category.lower():
                    category_cap = percentage
                    break
            effective_reduction_percentage = category_cap

        monthly_savings = round(
            float(total_spent * effective_reduction_percentage) / 100, 2
        )
        new_budget = int(round(float(total_spent) - monthly_savings))
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
