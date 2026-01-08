
from sqlalchemy.orm import Session
from app.models.budget import Budget
from app.schemas.budget import BudgetCreate, BudgetUpdate
from datetime import date
from fastapi import HTTPException
from app.crud.bank import get_total_spending_for_category_and_month
from app.models.user import User


def get_budgets_by_user(db: Session, user_id: str):
    return db.query(Budget).filter(Budget.user_id == user_id).all()

def get_budget_by_id(db: Session, budget_id: str, user_id: str):
    return db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == user_id).first()

def get_budget_by_category_and_user_and_date(db: Session, user_id: str, category: str, start_date: date, end_date: date):
    return db.query(Budget).filter(
        Budget.user_id == user_id,
        Budget.category == category,
        Budget.start_date <= end_date,
        Budget.end_date >= start_date
    ).first()

def create_budget(db: Session, budget: BudgetCreate, user_id: str):
    # Enforce budget creation rule
    current_month_spending = get_total_spending_for_category_and_month(
        db,
        user_id,
        budget.category,
        budget.start_date.year,
        budget.start_date.month
    )
    
    if not (current_month_spending - 1000 <= budget.budget_amount <= current_month_spending + 1000):
        raise HTTPException(
            status_code=400,
            detail=f"Budget for category '{budget.category}' must be within ± Rs 1000 of current month's spending (Rs {current_month_spending:.2f})."
        )

    db_budget = Budget(**budget.dict(), user_id=user_id)
    db.add(db_budget)
    db.commit()
    db.refresh(db_budget)
    return db_budget

def update_budget(db: Session, budget_id: str, budget: BudgetUpdate, user_id: str):
    db_budget = get_budget_by_id(db, budget_id=budget_id, user_id=user_id)
    if db_budget:
        db_budget.budget_amount = budget.budget_amount
        db.commit()
        db.refresh(db_budget)
    return db_budget

def delete_budget(db: Session, budget_id: str, user_id: str):
    db_budget = get_budget_by_id(db, budget_id=budget_id, user_id=user_id)
    if db_budget:
        db.delete(db_budget)
        db.commit()
    return db_budget

def evaluate_budget_completion(db: Session, budget: Budget, user: User) -> bool:
    """
    Evaluates if a budget goal is met, grants XP, and calculates savings.
    Returns True if the budget was met or exceeded, False otherwise.
    """
    total_spending = get_total_spending_for_category_and_month(
        db,
        user.user_id,
        budget.category,
        budget.start_date.year,
        budget.start_date.month
    )

    if total_spending <= budget.budget_amount:
        # Budget goal successful
        # Grant XP (e.g., 100 XP per successful goal)
        user.total_xp += 100 
        
        # Calculate and persist savings
        if budget.budget_amount > total_spending:
            savings = budget.budget_amount - total_spending
            user.savings += int(savings) # Ensure savings are integers
            print(f"User {user.user_id} saved Rs {savings:.2f} for budget {budget.id}")
        
        db.add(user)
        db.commit()
        db.refresh(user)

        return True
    return False

def update_completed_budgets_for_user(db: Session, user_id: str):
    """
    Checks and updates the status of completed budgets for a user.
    """
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return

    today = date.today()
    uncompleted_budgets = db.query(Budget).filter(
        Budget.user_id == user_id,
        Budget.end_date < today,
        Budget.is_completed == False
    ).all()

    for budget in uncompleted_budgets:
        if evaluate_budget_completion(db, budget, user):
            user.goals_completed += 1
        
        budget.is_completed = True
        db.add(budget)
    
    db.commit()
    db.refresh(user)

