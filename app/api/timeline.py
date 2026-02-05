from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.event_logger import fetch_user_timeline
from app.schemas.token import TokenData
from app.utils.deps import get_current_user
from app.models.user import User

router = APIRouter()


@router.get("/timeline/me", tags=["timeline"])
def get_my_timeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    events = fetch_user_timeline(db, user_id=str(current_user.id))
    return [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "payload": event.payload,
            "created_at": event.created_at,
        }
        for event in events
    ]
