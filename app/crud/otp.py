from sqlalchemy.orm import Session
from app.models.otp import OTP
import datetime

def create_otp(db: Session, user_id: int, otp_code: str, expires_in_minutes: int = 5):
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=expires_in_minutes)
    db_otp = OTP(user_id=user_id, otp_code=otp_code, expires_at=expires_at)
    db.add(db_otp)
    db.commit()
    db.refresh(db_otp)
    return db_otp

def get_otp_by_user_id(db: Session, user_id: int):
    return db.query(OTP).filter(OTP.user_id == user_id).first()

def delete_otp(db: Session, db_otp: OTP):
    db.delete(db_otp)
    db.commit()
