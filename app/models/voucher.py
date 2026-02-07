import uuid
import enum
from sqlalchemy import (
    Column,
    String,
    DateTime,
    Float,
    Integer,
    Boolean,
    ForeignKey,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.base import Base


class DiscountType(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class VoucherStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"


class VoucherTemplate(Base):
    __tablename__ = "voucher_templates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    discount_type = Column(SQLAlchemyEnum(DiscountType), nullable=False)
    discount_value = Column(Float, nullable=False)
    minimum_spend = Column(Float, nullable=True)
    tier_required = Column(Integer, nullable=True)
    xp_required = Column(Integer, nullable=True)
    validity_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class UserVoucher(Base):
    __tablename__ = "user_vouchers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    voucher_template_id = Column(
        UUID(as_uuid=True), ForeignKey("voucher_templates.id"), nullable=False
    )
    code = Column(String, unique=True, nullable=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        SQLAlchemyEnum(VoucherStatus), nullable=False, default=VoucherStatus.ACTIVE
    )
