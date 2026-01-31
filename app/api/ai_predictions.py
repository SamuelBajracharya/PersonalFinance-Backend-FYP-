from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.deps import get_db, get_current_user
from app.crud.budget import get_budgets_by_user
from app.crud.daily_prediction import create_daily_prediction
from app.schemas.ai_predictions import BudgetPrediction, DailyPredictionCreate
from ai.inference import predict_next_day
from decimal import Decimal
from app.models.user import User # Import the User model

router = APIRouter()

@router.get("/predict/budgets/", response_model=list[BudgetPrediction])
def predict_budget_for_user(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate budget predictions for the authenticated user and store them.
    """
    user_id = current_user.user_id # Get user_id from the authenticated user
    
    budgets = get_budgets_by_user(db, user_id=user_id)
    if not budgets:
        raise HTTPException(status_code=404, detail="No budgets found for this user.")

    predictions = []
    for budget in budgets:
        try:
            (
                predicted_amount,
                risk_prob,
                risk_level,
                prediction_date,
                day_of_week,
                day_of_week_id,
                rolling_7_day_avg,
            ) = predict_next_day(
                user_id=user_id,
                category=budget.category,
                budget_remaining=budget.remaining_budget,
            )

            # Create and store the prediction
            prediction_to_store = DailyPredictionCreate(
                user_id=user_id,
                prediction_date=prediction_date,
                category=budget.category,
                day_of_week=day_of_week,
                day_of_week_id=day_of_week_id,
                rolling_7_day_avg=Decimal(float(rolling_7_day_avg)),
                budget_remaining=Decimal(budget.remaining_budget),
                predicted_amount=Decimal(float(predicted_amount)),
                risk_probability=Decimal(float(risk_prob)),
                risk_level=risk_level,
            )
            create_daily_prediction(db, prediction=prediction_to_store)

            # Append data for the response
            predictions.append(
                BudgetPrediction(
                    category=budget.category,
                    predicted_amount=predicted_amount,
                    risk_probability=risk_prob,
                    risk_level=risk_level,
                    remaining_budget=budget.remaining_budget,
                    prediction_date=prediction_date,
                )
            )
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"Error predicting for category {budget.category}: {e}")
            continue

    if not predictions:
        raise HTTPException(
            status_code=404,
            detail="Could not generate predictions. Models for the user's budget categories may not be available.",
        )

    return predictions