from sqlalchemy.orm import Session
import uuid

from app.models.bank import BankAccount, Transaction
from app.schemas.bank import TransactionCreate

def get_bank_account(db: Session, bank_account_id: uuid.UUID):
    return db.query(BankAccount).filter(BankAccount.id == bank_account_id).first()

def get_bank_accounts_by_user(db: Session, user_id: str):
    return db.query(BankAccount).filter(BankAccount.user_id == user_id).all()

def create_transaction(db: Session, transaction: TransactionCreate, user_id: str):
    db_transaction = Transaction(**transaction.model_dump(), user_id=user_id)
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction

def get_transactions_by_account(db: Session, account_id: uuid.UUID):
    return db.query(Transaction).filter(Transaction.account_id == account_id).all()