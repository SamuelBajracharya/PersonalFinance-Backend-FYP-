from sqlalchemy.orm import Session
from app.models.financial_event import FinancialEvent
from sqlalchemy.exc import SQLAlchemyError
from typing import Any, Dict, List
import logging
import threading
from app.db.session import SessionLocal


def log_event_async(
    _unused_db: Session,
    user_id: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: Dict[str, Any],
):
    def _log():
        db = SessionLocal()
        try:
            event = FinancialEvent(
                user_id=user_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
            )
            db.add(event)
            db.commit()
        except SQLAlchemyError as e:
            db.rollback()
            logging.error(f"Failed to log event: {e}")
        finally:
            db.close()

    threading.Thread(target=_log, daemon=True).start()


def fetch_user_timeline(db: Session, user_id: str) -> List[FinancialEvent]:
    return (
        db.query(FinancialEvent)
        .filter(FinancialEvent.user_id == user_id)
        .order_by(FinancialEvent.created_at.desc())
        .all()
    )
