from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from typing import List

from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.goal import Goal, GoalCreate, GoalImpactAnalysis
from app.crud.goal import create_goal, get_goals_by_user
from app.services.goal_progress import build_goal_impact_analysis

router = APIRouter()


@router.post("/", response_model=Goal, status_code=status.HTTP_201_CREATED)
def create_financial_goal(
    goal: GoalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if goal.target_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target amount must be positive.",
        )
    if goal.deadline <= date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deadline must be in the future.",
        )
    return create_goal(db, current_user.user_id, goal)


@router.get("/", response_model=List[Goal])
def list_goals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_goals_by_user(db, current_user.user_id)


@router.get("/impact", response_model=List[GoalImpactAnalysis])
def goal_impact_analysis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = build_goal_impact_analysis(db, current_user.user_id)
    return [GoalImpactAnalysis(**item) for item in analysis]
