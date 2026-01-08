from sqlalchemy.orm import Session
from sqlalchemy import func
import uuid
from datetime import datetime, timedelta

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

def get_transactions_by_user(db: Session, user_id: str):
    return db.query(Transaction).filter(Transaction.user_id == user_id).all()

def get_user_transactions_last_7_days(db: Session, user_id: str):
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    return db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.date >= seven_days_ago
    ).all()

def get_total_spending_for_category_and_month(
    db: Session, user_id: str, category: str, year: int, month: int
) -> float:
    start_of_month = datetime(year, month, 1)
    # Handle end of month for filtering
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1) - timedelta(microseconds=1)
    else:
        end_of_month = datetime(year, month + 1, 1) - timedelta(microseconds=1)

    total_spent = (
        db.query(func.sum(Transaction.amount))
        .filter(
            Transaction.user_id == user_id,
            Transaction.category == category,
            Transaction.date >= start_of_month,
            Transaction.date <= end_of_month,
            Transaction.type == "DEBIT",  # Only consider debit transactions for spending
        )
        .scalar()
    )
    return total_spent if total_spent is not None else 0.0