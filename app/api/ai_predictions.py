from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.deps import get_db, get_current_user
from app.crud.daily_prediction import get_latest_predictions_for_user
from app.schemas.ai_predictions import BudgetPrediction
from app.models.user import User  # Import the User model

router = APIRouter()


@router.get("/predict/budgets/", response_model=list[BudgetPrediction])
def get_latest_budget_predictions(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Fetch the latest stored budget predictions for the authenticated user.
    """
    user_id = current_user.user_id
    predictions = get_latest_predictions_for_user(db, user_id)
    if not predictions:
        raise HTTPException(
            status_code=404, detail="No predictions found for this user."
        )
    # Fetch sync status
    from app.crud.bank_sync_status import get_sync_status

    sync_status = get_sync_status(db, user_id)
    is_data_fresh = False
    last_successful_sync = None
    last_attempted_sync = None
    sync_status_value = None
    failure_reason = None
    if sync_status:
        last_successful_sync = sync_status.last_successful_sync
        last_attempted_sync = sync_status.last_attempted_sync
        sync_status_value = sync_status.sync_status
        failure_reason = sync_status.failure_reason
        # Data is fresh if last_successful_sync is today
        from datetime import date

        is_data_fresh = (
            last_successful_sync is not None
            and last_successful_sync.date() == date.today()
        )
    return [
        BudgetPrediction(
            category=p.category,
            predicted_amount=float(p.predicted_amount),
            risk_probability=float(p.risk_probability),
            risk_level=p.risk_level,
            remaining_budget=float(p.budget_remaining),
            prediction_date=p.prediction_date,
            is_data_fresh=is_data_fresh,
            last_successful_sync=last_successful_sync,
            last_attempted_sync=last_attempted_sync,
            sync_status=sync_status_value,
            failure_reason=failure_reason,
        )
        for p in predictions
    ]
