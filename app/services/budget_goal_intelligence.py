from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from statistics import mean

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.bank import Transaction
from app.models.budget import Budget
from app.models.daily_prediction import DailyPrediction


def _get_budget_for_user(db: Session, user_id: str, budget_id: str) -> Budget | None:
    return (
        db.query(Budget)
        .filter(Budget.id == budget_id, Budget.user_id == user_id)
        .first()
    )


def _sum_spend_for_period(
    db: Session,
    user_id: str,
    category: str,
    start_date: date,
    end_date: date,
) -> Decimal:
    period_start = datetime.combine(start_date, time.min)
    period_end = datetime.combine(end_date, time.max)

    total = (
        db.query(func.sum(Transaction.amount))
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == "DEBIT",
            Transaction.category == category,
            Transaction.date >= period_start,
            Transaction.date <= period_end,
        )
        .scalar()
    )
    return Decimal(total or 0)


def _average_daily_spend(
    db: Session,
    user_id: str,
    category: str,
    start_date: date,
    end_date: date,
) -> Decimal:
    spend = _sum_spend_for_period(db, user_id, category, start_date, end_date)
    days = max(1, (end_date - start_date).days + 1)
    return spend / Decimal(days)


def _latest_prediction_for_category(
    db: Session,
    user_id: str,
    category: str,
) -> DailyPrediction | None:
    return (
        db.query(DailyPrediction)
        .filter(
            DailyPrediction.user_id == user_id,
            DailyPrediction.category == category,
        )
        .order_by(DailyPrediction.prediction_date.desc())
        .first()
    )


def _build_micro_alerts(
    progress_percent: float,
    days_left: int,
    predicted_to_exceed: bool,
) -> list[dict]:
    alerts: list[dict] = []

    if progress_percent >= 95:
        alerts.append(
            {
                "level": "critical",
                "title": "Critical budget risk",
                "message": "You have already used more than 95% of this budget.",
            }
        )
    elif progress_percent >= 80:
        alerts.append(
            {
                "level": "high",
                "title": "High budget usage",
                "message": "You have crossed 80% of this budget. Reduce spending now.",
            }
        )
    elif progress_percent >= 60:
        alerts.append(
            {
                "level": "medium",
                "title": "Budget watch",
                "message": "You are above 60% spend. Track spending closely.",
            }
        )

    if predicted_to_exceed:
        alerts.append(
            {
                "level": "high",
                "title": "Projected overrun",
                "message": "At your current pace, this budget is likely to be exceeded.",
            }
        )

    if days_left <= 3 and progress_percent >= 80:
        alerts.append(
            {
                "level": "medium",
                "title": "Period ending soon",
                "message": "Only a few days remain and your spend is already high.",
            }
        )

    return alerts


def get_budget_goal_status(db: Session, user_id: str, budget_id: str) -> dict | None:
    budget = _get_budget_for_user(db, user_id, budget_id)
    if not budget:
        return None

    today = date.today()
    effective_end = min(today, budget.end_date)

    current_spend = _sum_spend_for_period(
        db,
        user_id,
        budget.category,
        budget.start_date,
        effective_end,
    )

    budget_amount = Decimal(budget.budget_amount)
    remaining = budget_amount - current_spend
    elapsed_days = max(1, (effective_end - budget.start_date).days + 1)
    days_left = max(0, (budget.end_date - today).days)

    burn_rate = current_spend / Decimal(elapsed_days)
    projected_spend = current_spend + (burn_rate * Decimal(days_left))

    prediction = _latest_prediction_for_category(db, user_id, budget.category)
    risk_level = str(getattr(prediction, "risk_level", "")).upper()
    predicted_to_exceed = projected_spend > budget_amount or risk_level == "HIGH"

    progress_percent = 0.0
    if budget_amount > 0:
        progress_percent = float((current_spend / budget_amount) * Decimal(100))

    alerts = _build_micro_alerts(
        progress_percent=progress_percent,
        days_left=days_left,
        predicted_to_exceed=predicted_to_exceed,
    )

    return {
        "budget_id": str(budget.id),
        "category": budget.category,
        "budget_amount": float(budget_amount),
        "current_spend": float(current_spend),
        "remaining_budget": float(remaining),
        "progress_percent": round(progress_percent, 2),
        "days_left": days_left,
        "burn_rate_per_day": round(float(burn_rate), 2),
        "projected_period_spend": round(float(projected_spend), 2),
        "predicted_to_exceed": predicted_to_exceed,
        "alerts": alerts,
    }


def get_all_budget_goal_statuses(db: Session, user_id: str) -> list[dict]:
    budgets = db.query(Budget).filter(Budget.user_id == user_id).all()
    statuses: list[dict] = []

    for budget in budgets:
        status = get_budget_goal_status(db, user_id, str(budget.id))
        if status:
            statuses.append(status)

    return statuses


def get_budget_prediction_explanation(
    db: Session,
    user_id: str,
    budget_id: str,
) -> dict | None:
    status = get_budget_goal_status(db, user_id, budget_id)
    if not status:
        return None

    prediction = _latest_prediction_for_category(db, user_id, status["category"])
    risk_level = str(getattr(prediction, "risk_level", "MEDIUM")).upper()
    risk_probability = float(getattr(prediction, "risk_probability", 0.5) or 0.5)

    today = date.today()
    last_7_start = today.fromordinal(today.toordinal() - 6)
    prev_7_start = today.fromordinal(today.toordinal() - 13)
    prev_7_end = today.fromordinal(today.toordinal() - 7)

    last_7_avg = _average_daily_spend(
        db, user_id, status["category"], last_7_start, today
    )
    prev_7_avg = _average_daily_spend(
        db,
        user_id,
        status["category"],
        prev_7_start,
        prev_7_end,
    )

    drivers: list[dict] = []

    if prev_7_avg > 0 and last_7_avg > prev_7_avg:
        increase_pct = float(((last_7_avg - prev_7_avg) / prev_7_avg) * Decimal(100))
        drivers.append(
            {
                "factor": "Recent spending trend",
                "impact": "high" if increase_pct >= 15 else "medium",
                "detail": f"Your last 7-day spend rate is up by {increase_pct:.1f}% compared to the previous week.",
            }
        )

    if status["progress_percent"] >= 80:
        drivers.append(
            {
                "factor": "Budget utilization",
                "impact": "high",
                "detail": "You have already consumed most of your budget for this period.",
            }
        )

    if risk_level == "HIGH":
        drivers.append(
            {
                "factor": "Model risk signal",
                "impact": "high",
                "detail": "The prediction model flagged this category as high risk for overrun.",
            }
        )

    if not drivers:
        drivers.append(
            {
                "factor": "Stable pattern",
                "impact": "low",
                "detail": "Recent spending pattern is stable and no major risk driver was detected.",
            }
        )

    short_explanation = (
        "You are likely to exceed this goal if current spending continues."
        if status["predicted_to_exceed"]
        else "You are currently on track for this goal if the same trend continues."
    )

    return {
        "budget_id": status["budget_id"],
        "category": status["category"],
        "risk_level": risk_level,
        "risk_probability": round(risk_probability, 4),
        "short_explanation": short_explanation,
        "drivers": drivers,
    }


def simulate_budget_goal(
    db: Session,
    user_id: str,
    budget_id: str,
    reduction_percent: float,
    absolute_cut: float,
) -> dict | None:
    status = get_budget_goal_status(db, user_id, budget_id)
    if not status:
        return None

    baseline_projected = Decimal(str(status["projected_period_spend"]))
    adjusted = baseline_projected

    if reduction_percent > 0:
        adjusted = (
            adjusted * (Decimal(100) - Decimal(str(reduction_percent))) / Decimal(100)
        )

    if absolute_cut > 0:
        adjusted = max(Decimal(0), adjusted - Decimal(str(absolute_cut)))

    budget_amount = Decimal(str(status["budget_amount"]))
    simulated_remaining = budget_amount - adjusted

    return {
        "budget_id": status["budget_id"],
        "category": status["category"],
        "baseline_projected_spend": float(baseline_projected),
        "simulated_projected_spend": round(float(adjusted), 2),
        "projected_savings": round(float(baseline_projected - adjusted), 2),
        "baseline_predicted_to_exceed": status["predicted_to_exceed"],
        "simulated_predicted_to_exceed": adjusted > budget_amount,
        "simulated_remaining_budget": round(float(simulated_remaining), 2),
    }


def get_budget_goal_suggestions(
    db: Session, user_id: str, budget_id: str
) -> dict | None:
    status = get_budget_goal_status(db, user_id, budget_id)
    if not status:
        return None

    suggestions: list[dict] = []

    daily_limit = 0.0
    if status["days_left"] > 0:
        daily_limit = max(0.0, status["remaining_budget"]) / status["days_left"]

    if status["predicted_to_exceed"]:
        suggestions.append(
            {
                "suggestion_type": "pace_control",
                "title": "Set a strict daily cap",
                "message": f"Keep {status['category']} spend under Rs {daily_limit:.0f}/day for the rest of this period.",
                "estimated_savings": max(
                    0.0, status["projected_period_spend"] - status["budget_amount"]
                ),
                "priority": "high",
            }
        )

    burn_rate = status["burn_rate_per_day"]
    if daily_limit > 0 and burn_rate > daily_limit:
        suggestions.append(
            {
                "suggestion_type": "trend_correction",
                "title": "Reduce daily burn rate",
                "message": f"Current burn rate is Rs {burn_rate:.0f}/day. Reduce by Rs {max(0.0, burn_rate - daily_limit):.0f}/day to stay on track.",
                "estimated_savings": max(
                    0.0, (burn_rate - daily_limit) * status["days_left"]
                ),
                "priority": "high",
            }
        )

    suggestions.append(
        {
            "suggestion_type": "nudge",
            "title": "Review the last 3 high-value spends",
            "message": f"Focus on your last {status['category']} transactions and delay one non-essential purchase.",
            "estimated_savings": round(max(50.0, status["budget_amount"] * 0.05), 2),
            "priority": "medium",
        }
    )

    suggestions.append(
        {
            "suggestion_type": "weekly_check",
            "title": "Set a mid-period check-in",
            "message": "Schedule a weekly review to compare actual spend vs target and correct early.",
            "estimated_savings": round(max(25.0, status["budget_amount"] * 0.03), 2),
            "priority": "medium",
        }
    )

    # Keep smart suggestions bounded for the client UI.
    suggestions = suggestions[:4]

    return {
        "budget_id": status["budget_id"],
        "category": status["category"],
        "suggestions": suggestions,
    }


def get_adaptive_budget_adjustment(
    db: Session,
    user_id: str,
    budget_id: str,
) -> dict | None:
    budget = _get_budget_for_user(db, user_id, budget_id)
    if not budget:
        return None

    history = (
        db.query(Budget)
        .filter(
            Budget.user_id == user_id,
            Budget.category == budget.category,
            Budget.end_date < date.today(),
        )
        .order_by(Budget.end_date.desc())
        .limit(3)
        .all()
    )

    current_budget = Decimal(budget.budget_amount)

    if not history:
        status = get_budget_goal_status(db, user_id, budget_id)
        if status and status["predicted_to_exceed"]:
            recommended = current_budget * Decimal("1.10")
            reason = "No historical cycles found; current trend indicates likely overrun, so a 10% buffer is suggested."
        else:
            recommended = current_budget
            reason = "No historical cycles found; keeping current budget as baseline."
    else:
        realized_spends: list[Decimal] = []
        for entry in history:
            realized_spends.append(
                _sum_spend_for_period(
                    db,
                    user_id,
                    entry.category,
                    entry.start_date,
                    entry.end_date,
                )
            )

        avg_spend = Decimal(str(mean([float(item) for item in realized_spends])))

        if avg_spend > current_budget:
            recommended = avg_spend * Decimal("1.05")
            reason = "Recent closed cycles show repeated overruns; recommendation raises budget by 5% above your historical average spend."
        else:
            recommended = avg_spend * Decimal("1.03")
            reason = "Recent cycles are mostly within target; recommendation keeps budget lean with a small 3% flexibility margin."

    adjustment_percent = Decimal(0)
    if current_budget > 0:
        adjustment_percent = (
            (recommended - current_budget) / current_budget
        ) * Decimal(100)

    return {
        "budget_id": str(budget.id),
        "category": budget.category,
        "recommended_budget_amount": round(float(recommended), 2),
        "adjustment_percent": round(float(adjustment_percent), 2),
        "reason": reason,
    }


def get_budget_period_review(db: Session, user_id: str, budget_id: str) -> dict | None:
    budget = _get_budget_for_user(db, user_id, budget_id)
    if not budget:
        return None

    today = date.today()
    is_closed = budget.end_date < today
    effective_end = budget.end_date if is_closed else today

    total_spent = _sum_spend_for_period(
        db,
        user_id,
        budget.category,
        budget.start_date,
        effective_end,
    )

    budget_amount = Decimal(budget.budget_amount)
    achieved = total_spent <= budget_amount
    savings_or_overrun = budget_amount - total_spent

    if achieved:
        summary = (
            "Goal achieved. Spending stayed within budget for this period."
            if is_closed
            else "In progress and currently within budget."
        )
    else:
        summary = (
            "Goal missed. Spending exceeded budget in this period."
            if is_closed
            else "In progress but currently trending above budget."
        )

    recommended = get_adaptive_budget_adjustment(db, user_id, budget_id)
    next_recommended_budget = (
        recommended["recommended_budget_amount"]
        if recommended
        else float(budget_amount)
    )

    return {
        "budget_id": str(budget.id),
        "category": budget.category,
        "period_start": budget.start_date,
        "period_end": budget.end_date,
        "is_period_closed": is_closed,
        "achieved": achieved,
        "budget_amount": float(budget_amount),
        "total_spent": float(total_spent),
        "savings_or_overrun": round(float(savings_or_overrun), 2),
        "summary": summary,
        "next_recommended_budget": next_recommended_budget,
    }
