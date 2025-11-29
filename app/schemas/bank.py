from pydantic import BaseModel
import uuid
from datetime import datetime
from decimal import Decimal

class BankAccountBase(BaseModel):
    bank_name: str
    account_number_masked: str
    account_type: str
    balance: Decimal

class BankAccount(BankAccountBase):
    id: uuid.UUID
    user_id: uuid.UUID
    external_account_id: str

    class Config:
        from_attributes = True

class TransactionBase(BaseModel):
    source: str
    date: datetime
    amount: Decimal
    currency: str
    type: str
    status: str
    description: str | None = None
    merchant: str | None = None
    category: str | None = None

class TransactionCreate(TransactionBase):
    external_transaction_id: str | None = None
    account_id: uuid.UUID | None = None


class Transaction(TransactionBase):
    id: uuid.UUID
    user_id: uuid.UUID
    external_transaction_id: str | None = None
    account_id: uuid.UUID | None = None

    class Config:
        from_attributes = True