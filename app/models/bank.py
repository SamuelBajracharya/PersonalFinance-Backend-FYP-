
import uuid
from sqlalchemy import (
    Column,
    String,
    Numeric,
    ForeignKey,
    DateTime,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base
from app.models.user import User

class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    bank_name = Column(String, nullable=False)
    account_number_masked = Column(String, nullable=False)
    account_type = Column(String, nullable=False)
    balance = Column(Numeric(12, 2), nullable=False)

    user = relationship("User", back_populates="bank_accounts")
    transactions = relationship("Transaction", back_populates="account")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_transaction_id = Column(String, unique=True, nullable=True)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id"), nullable=True)
    source = Column(String, nullable=False)  # 'BANK' or 'MANUAL'
    date = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    type = Column(String(10), nullable=False)  # DEBIT/CREDIT
    status = Column(String(15), nullable=False)
    description = Column(String)
    merchant = Column(String)
    category = Column(String)

    user = relationship("User", back_populates="transactions")
    account = relationship("BankAccount", back_populates="transactions")
