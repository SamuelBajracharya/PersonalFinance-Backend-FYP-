from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from datetime import date, timedelta

from app import crud, schemas
from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.budget import (
    BudgetGoalAdaptiveAdjustment,
    BudgetGoalPeriodReview,
    BudgetGoalPredictionExplanation,
    BudgetGoalSimulationRequest,
    BudgetGoalSimulationResult,
    BudgetGoalStatus,
    BudgetGoalSuggestionsResponse,
)
from app.services.budget_goal_intelligence import (
    get_adaptive_budget_adjustment,
    get_all_budget_goal_statuses,
    get_budget_goal_status,
    get_budget_goal_suggestions,
    get_budget_period_review,
    get_budget_prediction_explanation,
    simulate_budget_goal,
)

router = APIRouter()


@router.post("/", response_model=schemas.Budget, status_code=status.HTTP_201_CREATED)
def create_budget(
    budget: schemas.BudgetCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start_date = date.today()
    end_date = start_date + timedelta(days=30)

    existing_budget = crud.budget.get_budget_by_category_and_user_and_date(
        db=db,
        user_id=current_user.user_id,
        category=budget.category,
        start_date=start_date,
        end_date=end_date,
    )
    if existing_budget:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A budget for this category and month already exists.",
        )

    if budget.budget_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Budget amount must be positive.",
        )

    db_budget = crud.budget.create_budget(
        db=db, budget=budget, user_id=current_user.user_id
    )
    # Trigger background tasks for predictions and budget evaluation
    from app.services.background_tasks import trigger_predictions_and_budget_evaluation

    background_tasks.add_task(
        trigger_predictions_and_budget_evaluation, current_user.user_id
    )
    return db_budget


@router.get("/", response_model=List[schemas.Budget])
def read_budgets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.budget.get_budgets_by_user(db=db, user_id=current_user.user_id)


@router.get("/goal-status", response_model=List[BudgetGoalStatus])
def get_budget_goal_statuses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_all_budget_goal_statuses(db, current_user.user_id)


@router.get("/{budget_id}/goal-status", response_model=BudgetGoalStatus)
def get_single_budget_goal_status(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    status_payload = get_budget_goal_status(db, current_user.user_id, budget_id)
    if not status_payload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    return status_payload


@router.get(
    "/{budget_id}/prediction-explanation",
    response_model=BudgetGoalPredictionExplanation,
)
def get_budget_goal_prediction_explanation(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    explanation = get_budget_prediction_explanation(db, current_user.user_id, budget_id)
    if not explanation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    return explanation


@router.post("/{budget_id}/simulate", response_model=BudgetGoalSimulationResult)
def simulate_budget_goal_outcome(
    budget_id: str,
    payload: BudgetGoalSimulationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    simulation = simulate_budget_goal(
        db,
        current_user.user_id,
        budget_id,
        payload.reduction_percent,
        payload.absolute_cut,
    )
    if not simulation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    return simulation


@router.get("/{budget_id}/suggestions", response_model=BudgetGoalSuggestionsResponse)
def get_goal_suggestions(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    suggestions = get_budget_goal_suggestions(db, current_user.user_id, budget_id)
    if not suggestions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    return suggestions


@router.get(
    "/{budget_id}/adaptive-adjustment",
    response_model=BudgetGoalAdaptiveAdjustment,
)
def get_goal_adaptive_adjustment(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recommendation = get_adaptive_budget_adjustment(db, current_user.user_id, budget_id)
    if not recommendation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    return recommendation


@router.get("/{budget_id}/review", response_model=BudgetGoalPeriodReview)
def get_goal_period_review(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    review = get_budget_period_review(db, current_user.user_id, budget_id)
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Budget not found",
        )
    return review


@router.put("/{budget_id}", response_model=schemas.Budget)
def update_budget(
    budget_id: str,
    budget: schemas.BudgetUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_budget = crud.budget.get_budget_by_id(
        db=db, budget_id=budget_id, user_id=current_user.user_id
    )
    if not db_budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        )

    if budget.budget_amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Budget amount must be positive.",
        )

    db_budget = crud.budget.update_budget(
        db=db, budget_id=budget_id, budget=budget, user_id=current_user.user_id
    )
    # Trigger background tasks for predictions and budget evaluation
    from app.services.background_tasks import trigger_predictions_and_budget_evaluation

    background_tasks.add_task(
        trigger_predictions_and_budget_evaluation, current_user.user_id
    )
    return db_budget


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_budget(
    budget_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_budget = crud.budget.get_budget_by_id(
        db=db, budget_id=budget_id, user_id=current_user.user_id
    )
    if not db_budget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found"
        )

    crud.budget.delete_budget(db=db, budget_id=budget_id, user_id=current_user.user_id)
    return
