from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.bank import Transaction
from app.models.user import User
from app.schemas.what_if_scenarios import WhatIfScenario, WhatIfPreferences

from app.services.event_logger import log_event_async


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _normalize_category(value: str) -> str:
    return (value or "").strip().lower()


def _build_dynamic_reduction_rate(
    total_spend: float,
    max_total_spend: float,
    transaction_count: int,
    variability_cv: float,
    trend_ratio: float,
) -> int:
    # Heuristic model from behavior features:
    # - total spend intensity
    # - spending frequency
    # - variability (std/mean)
    # - trend (second-half spend vs first-half spend)
    spend_intensity = total_spend / max(max_total_spend, 1.0)
    frequency_score = min(transaction_count / 20.0, 1.0)
    variability_score = min(variability_cv / 1.5, 1.0)
    upward_trend_score = max(0.0, min(trend_ratio, 1.0))

    reduction = (
        8.0
        + (18.0 * spend_intensity)
        + (6.0 * frequency_score)
        + (8.0 * variability_score)
        + (8.0 * upward_trend_score)
    )
    return int(round(_clamp(reduction, 5.0, 45.0)))


def _apply_preferences(
    category: str,
    reduction_pct: int,
    preferences: WhatIfPreferences | None,
) -> int:
    if preferences is None:
        return reduction_pct

    normalized_category = _normalize_category(category)
    protected_categories = {
        _normalize_category(c) for c in (preferences.protected_categories or [])
    }

    adjusted = reduction_pct

    if normalized_category in protected_categories:
        adjusted = min(adjusted, int(preferences.protected_category_cap))

    category_caps = {
        _normalize_category(k): int(v)
        for k, v in (preferences.category_caps or {}).items()
    }
    if normalized_category in category_caps:
        adjusted = min(adjusted, category_caps[normalized_category])

    if preferences.global_min_reduction is not None:
        adjusted = max(adjusted, int(preferences.global_min_reduction))

    if preferences.global_max_reduction is not None:
        adjusted = min(adjusted, int(preferences.global_max_reduction))

    return int(_clamp(adjusted, 1, 60))


def get_what_if_scenarios(
    db: Session,
    user: User,
    preferences: WhatIfPreferences | None = None,
) -> list[WhatIfScenario]:
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
            func.count(Transaction.id).label("txn_count"),
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

    max_total_spend = max(float(row.total_spent or 0) for row in top_categories)

    scenarios = []
    for category, total_spent, txn_count in top_categories:
        # Only include categories with positive spending
        if not total_spent or float(total_spent) <= 0:
            continue

        category_tx = (
            db.query(Transaction.amount, Transaction.date)
            .filter(
                Transaction.user_id == user.user_id,
                Transaction.type == "DEBIT",
                Transaction.category == category,
                Transaction.date
                >= datetime.combine(last_month_start, datetime.min.time()),
                Transaction.date
                <= datetime.combine(last_month_end, datetime.max.time()),
            )
            .all()
        )

        amounts = [float(tx.amount or 0) for tx in category_tx]
        tx_count = len(amounts)
        mean_amount = (sum(amounts) / tx_count) if tx_count > 0 else 0.0
        if tx_count > 1 and mean_amount > 0:
            variance = sum((amount - mean_amount) ** 2 for amount in amounts) / tx_count
            std_dev = variance**0.5
            variability_cv = std_dev / mean_amount
        else:
            variability_cv = 0.0

        month_mid = last_month_start + timedelta(days=14)
        first_half_spend = sum(
            float(tx.amount or 0)
            for tx in category_tx
            if tx.date and tx.date.date() <= month_mid
        )
        second_half_spend = sum(
            float(tx.amount or 0)
            for tx in category_tx
            if tx.date and tx.date.date() > month_mid
        )
        trend_ratio = 0.0
        if first_half_spend > 0:
            trend_ratio = (second_half_spend - first_half_spend) / first_half_spend

        model_reduction = _build_dynamic_reduction_rate(
            total_spend=float(total_spent),
            max_total_spend=max_total_spend,
            transaction_count=int(txn_count or 0),
            variability_cv=variability_cv,
            trend_ratio=trend_ratio,
        )

        effective_reduction_percentage = _apply_preferences(
            category=category,
            reduction_pct=model_reduction,
            preferences=preferences,
        )

        monthly_savings = round(
            float(total_spent * effective_reduction_percentage) / 100, 2
        )
        new_budget = float(round(float(total_spent) - monthly_savings, 2))
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
        {
            "scenarios": [s.__dict__ for s in scenarios],
            "preferences": preferences.model_dump() if preferences else None,
        },
    )
    return scenarios
