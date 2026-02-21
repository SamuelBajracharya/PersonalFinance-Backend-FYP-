from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.utils.deps import get_db, get_current_user
from app.crud.daily_prediction import get_latest_predictions_for_user
from app.schemas.ai_predictions import BudgetPrediction, StockPrediction
from app.models.user import User  # Import the User model
from app.services.stock_predictions import (
    predict_for_instrument,
    predict_for_user_instruments,
)

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


@router.get("/predict/stocks/", response_model=list[StockPrediction])
def get_stock_predictions(
    instrument: str | None = Query(
        default=None,
        description="Optional ticker symbol (e.g., AAPL). If omitted, predicts user's synced instruments.",
    ),
    horizon_days: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Prediction horizon in days.",
    ),
    confidence_level: float = Query(
        default=0.95,
        gt=0,
        lt=1,
        description="Confidence level for confidence interval.",
    ),
    force_source: str = Query(
        default="auto",
        description="Data source preference: auto | mock | placeholder.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Predict stock returns using the stock model.
    - Without instrument: predicts for all synced instruments invested by the user.
    - With instrument: predicts for the requested symbol (even if not in user's portfolio).
    """
    try:
        if instrument:
            prediction = predict_for_instrument(
                db=db,
                user_id=current_user.user_id,
                instrument=instrument,
                horizon_days=horizon_days,
                confidence_level=confidence_level,
                force_source=force_source,
            )
            return [StockPrediction(**prediction)]

        predictions = predict_for_user_instruments(
            db=db,
            user_id=current_user.user_id,
            horizon_days=horizon_days,
            confidence_level=confidence_level,
            force_source=force_source,
        )
        if not predictions:
            raise HTTPException(
                status_code=404,
                detail="No synced stock instruments found for this user. Sync bank data first or pass ?instrument=SYMBOL.",
            )
        return [StockPrediction(**prediction) for prediction in predictions]
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate stock predictions: {exc}",
        ) from exc
