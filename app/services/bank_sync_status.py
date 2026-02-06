# ...existing code...
from app.crud.bank_sync_status import update_sync_status
from app.models import SyncStatusEnum
from datetime import datetime

# Call this function after sync attempts


def record_bank_sync_attempt(
    db, user_id: str, success: bool, failure_reason: str = None
):
    now = datetime.utcnow()
    status = SyncStatusEnum.SUCCESS if success else SyncStatusEnum.FAILED
    update_sync_status(
        db=db,
        user_id=user_id,
        attempted=now,
        success=now if success else None,
        status=status,
        failure_reason=failure_reason,
    )
