from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.goal import Goal, GoalStatus, GoalType
from app.models.bank import Transaction
from app.crud.goal import get_active_goals_by_user, update_goal
from app.crud.bank import get_user_transactions_last_30_days
from app.crud.daily_prediction import get_latest_predictions_for_user


_DEBT_CATEGORIES = {"debt", "loan", "emi", "credit card", "mortgage"}


def _calculate_financial_goal_xp(goal: Goal) -> int:
    completed_amount = Decimal(goal.current_amount)
    target_amount = Decimal(goal.target_amount)
    savings_amount = max(completed_amount, target_amount)

    # Dynamic XP by achieved savings amount
    if savings_amount < Decimal("5000"):
        return 15
    if savings_amount < Decimal("20000"):
        return 30
    if savings_amount < Decimal("50000"):
        return 60
    return 100


def _grant_goal_achievement_rewards(db: Session, user_id: str, goal: Goal):
    from app.models.user import User
    from app.services.event_logger import log_event_async

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return

    earned_xp = _calculate_financial_goal_xp(goal)
    user.total_xp = (user.total_xp or 0) + earned_xp
    db.add(user)
    db.commit()
    db.refresh(user)

    log_event_async(
        db,
        user_id,
        "goal_completed",
        "goal",
        str(goal.id),
        {
            "goal_type": str(goal.goal_type),
            "target_amount": float(goal.target_amount),
            "current_amount": float(goal.current_amount),
            "xp_gained": earned_xp,
        },
    )

    # Achievement voucher for goal completion, aligned with current XP tier
    try:
        from app.services.voucher_service import (
            issue_voucher_for_tier,
            derive_tier_from_xp,
        )

        achievement_tier = derive_tier_from_xp(db, user.total_xp or 0)
        issue_voucher_for_tier(db, str(user.user_id), achievement_tier)
    except Exception:
        pass

    # Re-evaluate rewards after XP change (also handles 500 XP vouchers)
    try:
        from app.services.reward_evaluation import evaluate_rewards

        evaluate_rewards(db, user)
    except Exception:
        pass


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
    from app.services.event_logger import log_event_async

    for goal in goals:
        delta = _apply_transaction_delta(goal, transaction)
        if delta != 0:
            new_amount = Decimal(goal.current_amount) + delta
            if new_amount < 0:
                new_amount = Decimal(0)
            goal.current_amount = new_amount
            # Audit log for manual transactions affecting goals
            if getattr(transaction, "source", None) == "MANUAL":
                log_event_async(
                    db,
                    user_id,
                    "manual_transaction_goal_update",
                    "goal",
                    str(goal.id),
                    {
                        "goal_id": str(goal.id),
                        "goal_type": str(goal.goal_type),
                        "transaction_id": str(transaction.id),
                        "amount": float(transaction.amount),
                        "date": transaction.date.isoformat(),
                        "type": transaction.type,
                        "category": transaction.category,
                        "source": transaction.source,
                        "new_goal_amount": float(new_amount),
                    },
                )
        previous_status = goal.status
        _update_goal_status(goal, today)
        update_goal(db, goal)

        if (
            previous_status != GoalStatus.ACHIEVED
            and goal.status == GoalStatus.ACHIEVED
        ):
            _grant_goal_achievement_rewards(db, user_id, goal)


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

    # Separate manual and bank progress
    manual_income = sum(
        t.amount
        for t in transactions
        if t.type == "CREDIT" and getattr(t, "source", None) == "MANUAL"
    )
    manual_expenses = sum(
        t.amount
        for t in transactions
        if t.type == "DEBIT" and getattr(t, "source", None) == "MANUAL"
    )
    bank_income = sum(
        t.amount
        for t in transactions
        if t.type == "CREDIT" and getattr(t, "source", None) == "BANK"
    )
    bank_expenses = sum(
        t.amount
        for t in transactions
        if t.type == "DEBIT" and getattr(t, "source", None) == "BANK"
    )
    manual_savings = Decimal(manual_income - manual_expenses)
    bank_savings = Decimal(bank_income - bank_expenses)

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
                "manual_savings": manual_savings,
                "bank_savings": bank_savings,
            }
        )

    return analysis
