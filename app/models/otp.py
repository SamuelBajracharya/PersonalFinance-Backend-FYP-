import uuid
import enum
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class OtpPurpose(str, enum.Enum):
    ACCOUNT_VERIFICATION = "account_verification"
    TWO_FACTOR_AUTH = "two_factor_auth"
    PASSWORD_RESET = "password_reset"


class OTP(Base):
    __tablename__ = "otps"

    otp_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    code = Column(String, nullable=False)  # OTP code
    purpose = Column(
        SAEnum(OtpPurpose, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="otps")
