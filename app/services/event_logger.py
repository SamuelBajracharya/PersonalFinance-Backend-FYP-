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
    import datetime, decimal, json

    def make_json_safe(obj):
        if isinstance(obj, dict):
            return {k: make_json_safe(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_json_safe(v) for v in obj]
        elif isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        elif isinstance(obj, decimal.Decimal):
            return float(obj)
        else:
            return obj

    def _log():
        db = SessionLocal()
        try:
            safe_payload = make_json_safe(payload)
            event = FinancialEvent(
                user_id=user_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=safe_payload,
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
