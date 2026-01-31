from sqlalchemy.orm import Session
from app.models.daily_prediction import DailyPrediction
from app.schemas.ai_predictions import DailyPredictionCreate

def create_daily_prediction(db: Session, prediction: DailyPredictionCreate) -> DailyPrediction:
    db_prediction = DailyPrediction(**prediction.dict())
    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)
    return db_prediction
