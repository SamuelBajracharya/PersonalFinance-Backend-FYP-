from app.models import BankSyncStatus, SyncStatusEnum
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional


def get_or_create_sync_status(db: Session, user_id: str) -> BankSyncStatus:
    sync_status = (
        db.query(BankSyncStatus).filter(BankSyncStatus.user_id == user_id).first()
    )
    if not sync_status:
        sync_status = BankSyncStatus(user_id=user_id)
        db.add(sync_status)
        db.commit()
        db.refresh(sync_status)
    return sync_status


def update_sync_status(
    db: Session,
    user_id: str,
    attempted: Optional[datetime] = None,
    success: Optional[datetime] = None,
    last_tx_fetched: Optional[datetime] = None,
    status: Optional[SyncStatusEnum] = None,
    failure_reason: Optional[str] = None,
):
    sync_status = get_or_create_sync_status(db, user_id)
    if attempted:
        sync_status.last_attempted_sync = attempted
    if success:
        sync_status.last_successful_sync = success
    if last_tx_fetched:
        sync_status.last_transaction_fetched_at = last_tx_fetched
    if status:
        sync_status.sync_status = status
    if failure_reason is not None:
        sync_status.failure_reason = failure_reason
    db.add(sync_status)
    db.commit()
    db.refresh(sync_status)
    return sync_status


def get_sync_status(db: Session, user_id: str) -> Optional[BankSyncStatus]:
    return db.query(BankSyncStatus).filter(BankSyncStatus.user_id == user_id).first()
