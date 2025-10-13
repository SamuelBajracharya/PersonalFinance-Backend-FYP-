from sqlalchemy.orm import Session
from app.models import User
from app.schemas import UserCreate

def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: str):
    return db.query(User).filter(User.user_id == user_id).first()

def create_user(db: Session, user: UserCreate):
    db_user = User(email=user.email, name=user.name, hashed_password=user.password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def update_user_verified_status(db: Session, user_id: str, is_verified: bool):
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.is_verified = is_verified
        db.commit()
        db.refresh(db_user)
    return db_user

def update_user_password(db: Session, user_id: str, new_password: str):
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.hashed_password = new_password
        db.commit()
        db.refresh(db_user)
    return db_user