import uuid
from sqlalchemy import Column, String, DateTime, Enum as SQLAlchemyEnum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base import Base
import enum


class SyncStatusEnum(str, enum.Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class BankSyncStatus(Base):
    __tablename__ = "bank_sync_status"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, nullable=False, index=True)
    last_successful_sync = Column(DateTime(timezone=True), nullable=True)
    last_attempted_sync = Column(DateTime(timezone=True), nullable=True)
    last_transaction_fetched_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(SQLAlchemyEnum(SyncStatusEnum), nullable=True)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
