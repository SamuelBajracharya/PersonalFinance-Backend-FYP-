from sqlalchemy.orm import Session
from app.models import Reward, UserReward, User
from app.schemas import RewardCreate, UserRewardCreate
from typing import List, Optional
import uuid
from app.models.budget import Budget
from app.crud.bank import get_total_spending_for_category_and_month
from datetime import date

def get_reward_by_id(db: Session, reward_id: str):
    return db.query(Reward).filter(Reward.id == reward_id).first()

def get_all_rewards(db: Session) -> List[Reward]:
    return db.query(Reward).all()

def get_user_reward(db: Session, user_id: str, reward_id: str):
    return db.query(UserReward).filter(UserReward.user_id == user_id, UserReward.reward_id == reward_id).first()

def create_user_reward(db: Session, user_reward_in: UserRewardCreate) -> UserReward:
    db_user_reward = UserReward(**user_reward_in.dict())
    db.add(db_user_reward)
    db.commit()
    db.refresh(db_user_reward)
    return db_user_reward

def get_completed_budget_goals_count_for_user(db: Session, user_id: str) -> int:
    """
    Counts the number of successfully completed budget goals for a user.
    A budget is considered completed if the total spending for its category
    and period is less than or equal to the budgeted amount.
    """
    completed_goals_count = 0
    current_date = date.today()
    
    # Get all budgets for the user
    user_budgets = db.query(Budget).filter(Budget.user_id == user_id).all()
    
    for budget in user_budgets:
        # Only evaluate budgets whose period has ended
        if budget.end_date < current_date: # Only check past budgets
            total_spending = get_total_spending_for_category_and_month(
                db,
                user_id,
                budget.category,
                budget.start_date.year,
                budget.start_date.month
            )
            
            if total_spending <= budget.budget_amount:
                completed_goals_count += 1
                
    return completed_goals_count