# app/api/bank_routes.py
from fastapi import APIRouter, Depends, HTTPException, status, Form, BackgroundTasks
from sqlalchemy.orm import Session
import uuid
from typing import List

from app import crud, schemas
from app.utils.deps import get_db, get_current_user
from app.models.user import User
from app.services.bank_sync import login_and_sync_all_accounts

router = APIRouter()


@router.post("/bank-login", status_code=status.HTTP_200_OK)
async def login_to_bank_and_sync(
    username: str = Form(...),
    password: str = Form(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Logs into the user's bank using form-data credentials.
    Automatically syncs the first returned account.
    """

    # 1. Login to bank API

    sync_summary = await login_and_sync_all_accounts(
        user_id=current_user.user_id,
        username=username,
        password=password,
        db=db,
    )

    # Update sync status metadata
    from app.services.bank_sync_status import record_bank_sync_attempt

    success = sync_summary["status"] == "success"
    failure_reason = sync_summary["message"] if not success else None
    record_bank_sync_attempt(db, current_user.user_id, success, failure_reason)

    if sync_summary["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sync_summary["message"],
        )

    # Trigger background tasks for predictions and budget evaluation
    if background_tasks is not None:
        from app.services.background_tasks import (
            trigger_predictions_and_budget_evaluation,
        )

        background_tasks.add_task(
            trigger_predictions_and_budget_evaluation, current_user.user_id
        )

    return sync_summary


@router.post("/unlink", status_code=status.HTTP_200_OK)
def unlink_bank_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Unlinks all bank accounts for the current user by deactivating them.
    Transaction data is preserved, but the accounts will no longer be synced.
    """
    crud.deactivate_bank_accounts_by_user(db=db, user_id=current_user.user_id)
    return {"message": "All bank accounts have been unlinked successfully."}


@router.delete("/delete-data", status_code=status.HTTP_200_OK)
def delete_user_transaction_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Deletes all transaction data for the current user.
    """
    crud.delete_transactions_by_user(db=db, user_id=current_user.user_id)
    return {"message": "All transaction data has been deleted successfully."}


@router.get("/accounts", response_model=List[schemas.BankAccount])
def read_bank_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_bank_accounts_by_user(db=db, user_id=current_user.user_id)


@router.post("/transactions", response_model=schemas.Transaction)
def create_transaction(
    transaction: schemas.TransactionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ensure user owns the account
    db_account = crud.get_bank_account(db, transaction.account_id)
    if not db_account or db_account.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Unauthorized for this account")
    # Limit manual transaction impact
    if transaction.source == "MANUAL":
        # Cap amount for manual transactions: 20% of largest active goal
        from app.crud.goal import get_active_goals_by_user

        active_goals = get_active_goals_by_user(db, current_user.user_id)
        if not active_goals:
            raise HTTPException(
                status_code=400,
                detail="No active financial goals found. Manual transaction not allowed.",
            )
        max_goal_amount = max([float(goal.target_amount) for goal in active_goals])
        dynamic_cap = max_goal_amount * 0.2
        min_cap = 200
        max_cap = 2000
        allowed_cap = min(max(dynamic_cap, min_cap), max_cap)
        if transaction.amount > allowed_cap:
            raise HTTPException(
                status_code=400,
                detail=f"Manual transaction amount exceeds allowed limit ({allowed_cap:.2f}). Limit is 20% of your largest goal, minimum 200, maximum 2,000.",
            )
        # Optionally restrict frequency (not implemented here, but can be added)

    db_transaction = crud.create_transaction(
        db=db, transaction=transaction, user_id=current_user.user_id
    )

    # Fraud-resistant: flag goals updated by manual transactions
    from app.utils.events import dispatcher, TransactionCreated

    payload = {
        "amount": float(db_transaction.amount),
        "currency": db_transaction.currency,
        "type": db_transaction.type,
        "status": db_transaction.status,
        "account_id": str(db_transaction.account_id),
        "date": db_transaction.date.isoformat(),
        "source": db_transaction.source,
        "is_manual": db_transaction.source == "MANUAL",
    }
    dispatcher.dispatch(
        TransactionCreated(db, current_user.user_id, str(db_transaction.id), payload)
    )

    # Trigger background tasks for predictions and budget evaluation
    from app.services.background_tasks import trigger_predictions_and_budget_evaluation

    background_tasks.add_task(
        trigger_predictions_and_budget_evaluation, current_user.user_id
    )

    return db_transaction


@router.get("/accounts/nabil", response_model=schemas.BankAccount)
def read_bank_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_bank_account = crud.get_bank_account_by_user_and_bank_name(
        db=db, user_id=current_user.user_id, bank_name="Nabil Bank"
    )
    if db_bank_account is None:
        raise HTTPException(
            status_code=404, detail="Nabil Bank account not found for the user"
        )
    return db_bank_account


@router.get("/accounts/nabil/transactions", response_model=List[schemas.Transaction])
def read_account_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_nabil_account = crud.get_bank_account_by_user_and_bank_name(
        db=db, user_id=current_user.user_id, bank_name="Nabil Bank"
    )
    if db_nabil_account is None:
        raise HTTPException(
            status_code=404, detail="Nabil Bank account not found for the user"
        )
    return crud.get_transactions_by_account(db=db, account_id=db_nabil_account.id)
