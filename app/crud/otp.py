from sqlalchemy.orm import Session
from app.models.otp import OTP, OtpPurpose
from datetime import datetime, timedelta, timezone

def create_otp(db: Session, user_id: str, code: str, purpose: OtpPurpose, expires_in_minutes: int = 5):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    db_otp = OTP(user_id=user_id, code=code, purpose=purpose, expires_at=expires_at)
    db.add(db_otp)
    db.commit()
    db.refresh(db_otp)
    return db_otp

def get_otp_by_user_id(db: Session, user_id: str, purpose: OtpPurpose):
    return db.query(OTP).filter(OTP.user_id == user_id, OTP.purpose == purpose).first()

def set_otp_as_used(db: Session, db_otp: OTP):
    db_otp.is_used = True
    db.add(db_otp)
    db.commit()
    db.refresh(db_otp)
    return db_otp

def delete_otp(db: Session, db_otp: OTP):
    db.delete(db_otp)
    db.commit()