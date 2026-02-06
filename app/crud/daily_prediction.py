from sqlalchemy import func
from sqlalchemy.orm import Session


def get_latest_predictions_for_user(db: Session, user_id: str):
    """
    Returns the latest prediction for each category for the user.
    """
    subquery = (
        db.query(
            DailyPrediction.category,
            func.max(DailyPrediction.prediction_date).label("max_date"),
        )
        .filter(DailyPrediction.user_id == user_id)
        .group_by(DailyPrediction.category)
        .subquery()
    )
    results = (
        db.query(DailyPrediction)
        .join(
            subquery,
            (DailyPrediction.category == subquery.c.category)
            & (DailyPrediction.prediction_date == subquery.c.max_date),
        )
        .filter(DailyPrediction.user_id == user_id)
        .all()
    )
    return results


from sqlalchemy.orm import Session
from app.models.daily_prediction import DailyPrediction
from app.schemas.ai_predictions import DailyPredictionCreate


def create_daily_prediction(
    db: Session, prediction: DailyPredictionCreate
) -> DailyPrediction:
    db_prediction = DailyPrediction(**prediction.dict())
    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)
    return db_prediction
