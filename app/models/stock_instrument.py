import uuid

from sqlalchemy import Column, String, Numeric, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class StockInstrument(Base):
    __tablename__ = "stock_instruments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    name = Column(String, nullable=True)
    quantity = Column(Numeric(18, 6), nullable=False, default=0)
    average_buy_price = Column(Numeric(18, 6), nullable=True)
    current_price = Column(Numeric(18, 6), nullable=True)
    currency = Column(String(10), nullable=True)
    external_instrument_id = Column(String, nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("user_id", "symbol", name="uq_user_symbol"),)

    user = relationship("User", back_populates="stock_instruments")
