from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.models.bank import BankAccount
from app.services.bank_sync import login_and_sync_all_accounts

router = APIRouter()


@router.post("/sync-now")
async def sync_now(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Find user's active bank account and token
    account = (
        db.query(BankAccount)
        .filter(
            BankAccount.user_id == current_user.user_id,
            BankAccount.is_active == True,
            BankAccount.bank_token != None,
        )
        .first()
    )
    if not account or not account.bank_token:
        raise HTTPException(
            status_code=400, detail="No active bank account or token found."
        )
    # Use stored token to sync
    sync_summary = await login_and_sync_all_accounts(
        user_id=current_user.user_id,
        username=None,
        password=None,
        db=db,
        bank_token=account.bank_token,
    )
    return sync_summary
