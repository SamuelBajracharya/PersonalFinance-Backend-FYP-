from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid
from typing import List

from app import crud, schemas
from app.utils.deps import get_db, get_current_user
from app.models.user import User

router = APIRouter()

@router.get("/accounts", response_model=List[schemas.BankAccount])
def read_bank_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.get_bank_accounts_by_user(db=db, user_id=current_user.user_id)

@router.get("/accounts/{account_id}", response_model=schemas.BankAccount)
def read_bank_account(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_bank_account = crud.get_bank_account(db=db, bank_account_id=account_id)
    if db_bank_account is None or db_bank_account.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return db_bank_account

@router.post("/transactions", response_model=schemas.Transaction)
def create_transaction(
    transaction: schemas.TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return crud.create_transaction(db=db, transaction=transaction, user_id=current_user.user_id)

@router.get("/accounts/{account_id}/transactions", response_model=List[schemas.Transaction])
def read_account_transactions(
    account_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_bank_account = crud.get_bank_account(db=db, bank_account_id=account_id)
    if db_bank_account is None or db_bank_account.user_id != current_user.user_id:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return crud.get_transactions_by_account(db=db, account_id=account_id)