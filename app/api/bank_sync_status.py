from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.schemas.bank_sync_status import BankSyncStatusSchema
from app.crud.bank_sync_status import get_sync_status
from app.utils.deps import get_db, get_current_user
from app.models.user import User

router = APIRouter()


@router.get("/sync-status", response_model=BankSyncStatusSchema)
def get_bank_sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sync_status = get_sync_status(db, current_user.user_id)
    if not sync_status:
        # Return empty/default if not found
        return BankSyncStatusSchema(user_id=current_user.user_id)
    return sync_status
