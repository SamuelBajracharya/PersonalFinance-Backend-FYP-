
from sqlalchemy.orm import Session
from app.models.budget import Budget
from app.schemas.budget import BudgetCreate, BudgetUpdate
from datetime import date

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
