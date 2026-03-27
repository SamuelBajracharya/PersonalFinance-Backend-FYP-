from fastapi import APIRouter, Depends, HTTPException, Header
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
    x_bank_token: str = Header(None, alias="X-Bank-Token"),
):
    # Try to get bank_token from X-Bank-Token header
    bank_token = x_bank_token

    # If not provided in header, fall back to DB
    account = None
    if not bank_token:
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
        bank_token = account.bank_token
    else:
        # If provided in header, get any active account for user (for updating token if needed)
        account = (
            db.query(BankAccount)
            .filter(
                BankAccount.user_id == current_user.user_id,
                BankAccount.is_active == True,
            )
            .first()
        )
        if not account:
            raise HTTPException(status_code=400, detail="No active bank account found.")

    # Use provided or stored token to sync
    sync_summary = await login_and_sync_all_accounts(
        user_id=current_user.user_id,
        username=None,
        password=None,
        db=db,
        bank_token=bank_token,
    )

    # If a new bank_token is returned, update it in the user's active bank account
    new_token = sync_summary.get("bank_token")
    if new_token and new_token != account.bank_token:
        account.bank_token = new_token
        db.commit()

    return sync_summary
