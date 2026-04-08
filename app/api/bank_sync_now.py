from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.services.bank_sync import (
    BankAccountAlreadyLinkedError,
    login_and_sync_all_accounts,
)

router = APIRouter()


class SyncNowRequest(BaseModel):
    bank_token: str


@router.post("/sync-now")
async def sync_now(
    payload: SyncNowRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bank_token = payload.bank_token

    # Use provided token from request body to sync.
    try:
        sync_summary = await login_and_sync_all_accounts(
            user_id=current_user.user_id,
            username=None,
            password=None,
            db=db,
            bank_token=bank_token,
        )
    except BankAccountAlreadyLinkedError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return sync_summary
