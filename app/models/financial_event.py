import uuid
from sqlalchemy import Column, String, DateTime, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base import Base


class FinancialEvent(Base):
    __tablename__ = "financial_events"
    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    user_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_financial_events_event_type", "event_type"),)
