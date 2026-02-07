from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.goal import Goal, GoalStatus, GoalType
from app.models.bank import Transaction
from app.crud.goal import get_active_goals_by_user, update_goal
from app.crud.bank import get_user_transactions_last_30_days
from app.crud.daily_prediction import get_latest_predictions_for_user


_DEBT_CATEGORIES = {"debt", "loan", "emi", "credit card", "mortgage"}


def _calculate_progress_percent(goal: Goal) -> float:
    if not goal.target_amount or goal.target_amount == 0:
        return 0.0
    return min(1.0, float(goal.current_amount) / float(goal.target_amount))


def _apply_transaction_delta(goal: Goal, transaction: Transaction) -> Decimal:
    amount = Decimal(transaction.amount)
    category = (transaction.category or "").strip().lower()

    if goal.goal_type in {GoalType.SAVINGS, GoalType.EMERGENCY, GoalType.TRAVEL}:
        if transaction.type == "CREDIT":
            return amount
        if transaction.type == "DEBIT":
            return -amount
        return Decimal(0)

    if goal.goal_type == GoalType.DEBT:
        if transaction.type == "DEBIT" and category in _DEBT_CATEGORIES:
            return amount
        return Decimal(0)

    return Decimal(0)


def _update_goal_status(goal: Goal, as_of: date, risk_signal: bool = False) -> bool:
    previous_status = goal.status
    if goal.current_amount >= goal.target_amount:
        goal.status = GoalStatus.ACHIEVED
    elif goal.deadline and as_of > goal.deadline:
        goal.status = GoalStatus.EXPIRED
    else:
        progress = _calculate_progress_percent(goal)
        if risk_signal and progress < 0.7:
            goal.status = GoalStatus.AT_RISK
        elif goal.deadline and (goal.deadline - as_of).days <= 14 and progress < 0.5:
            goal.status = GoalStatus.AT_RISK
        else:
            goal.status = GoalStatus.ACTIVE

    return goal.status != previous_status


def evaluate_goals_on_transaction(db: Session, user_id: str, transaction: Transaction):
    goals = get_active_goals_by_user(db, user_id)
    if not goals:
        return

    today = transaction.date.date() if transaction.date else date.today()
    for goal in goals:
        delta = _apply_transaction_delta(goal, transaction)
        if delta != 0:
            new_amount = Decimal(goal.current_amount) + delta
            if new_amount < 0:
                new_amount = Decimal(0)
            goal.current_amount = new_amount
        _update_goal_status(goal, today)
        update_goal(db, goal)


def evaluate_goals_on_prediction(db: Session, user_id: str, prediction_payload: dict):
    goals = get_active_goals_by_user(db, user_id)
    if not goals:
        return

    prediction_date = prediction_payload.get("prediction_date")
    as_of = prediction_date if isinstance(prediction_date, date) else date.today()
    risk_level = str(prediction_payload.get("risk_level", "")).upper()
    risk_signal = risk_level == "HIGH"

    for goal in goals:
        _update_goal_status(goal, as_of, risk_signal=risk_signal)
        update_goal(db, goal)


def build_goal_impact_analysis(db: Session, user_id: str) -> list[dict]:
    goals = get_active_goals_by_user(db, user_id)
    if not goals:
        return []

    transactions = get_user_transactions_last_30_days(db, user_id)
    total_income = sum(t.amount for t in transactions if t.type == "CREDIT")
    total_expenses = sum(t.amount for t in transactions if t.type == "DEBIT")
    recent_monthly_savings = Decimal(total_income - total_expenses)

    predictions = get_latest_predictions_for_user(db, user_id)
    predicted_monthly_spend = Decimal(
        sum((Decimal(p.predicted_amount) for p in predictions), Decimal(0))
    )
    predicted_monthly_savings = Decimal(total_income) - predicted_monthly_spend

    analysis = []
    today = date.today()
    for goal in goals:
        remaining = max(Decimal(goal.target_amount) - Decimal(goal.current_amount), 0)
        months_left = None
        if goal.deadline and goal.deadline >= today:
            days_left = (goal.deadline - today).days
            months_left = max(1, (days_left // 30) or 1)
        required_monthly = remaining if not months_left else (remaining / months_left)
        projected_months = None
        if predicted_monthly_savings > 0:
            projected_months = int(
                (remaining / predicted_monthly_savings) + Decimal("0.999")
            )

        is_on_track = False
        if months_left is not None and predicted_monthly_savings > 0:
            is_on_track = (
                projected_months is not None and projected_months <= months_left
            )

        analysis.append(
            {
                "goal_id": goal.id,
                "goal_type": goal.goal_type,
                "target_amount": goal.target_amount,
                "current_amount": goal.current_amount,
                "deadline": goal.deadline,
                "status": goal.status,
                "progress_percent": round(_calculate_progress_percent(goal) * 100, 2),
                "required_monthly_contribution": required_monthly,
                "projected_completion_months": projected_months,
                "is_on_track": is_on_track,
                "recent_monthly_savings": recent_monthly_savings,
                "predicted_monthly_savings": predicted_monthly_savings,
                "predicted_monthly_spend": predicted_monthly_spend,
            }
        )

    return analysis
