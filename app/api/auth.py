from fastapi import APIRouter, Depends, HTTPException
from app.crud import create_user, get_user_by_email, create_otp, get_otp_by_user_id, set_otp_as_used, delete_otp
from app.schemas import User, UserCreate, TempToken, UserLogin, Token, OtpRequest, OtpVerify
from app.models.otp import OtpPurpose
from app.utils import get_current_user, get_password_hash, get_db, get_current_user_from_temp_token
from sqlalchemy.orm import Session
from app.utils import (
    create_temp_token,
    verify_password,
    send_otp_email,
    create_access_token,
    create_refresh_token,
)
import random
import string
import datetime

router = APIRouter()


@router.post("/login", response_model=TempToken)
async def login_user(user_login: UserLogin, db: Session = Depends(get_db)):
    user = get_user_by_email(db, email=user_login.email)
    if not user or not verify_password(user_login.password, user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = {"id": user.user_id, "token_type": "temp"}
    temp_token = create_temp_token(data=token_data)

    return {
        "temp_token": temp_token,
        "message": "Login successful, please request an OTP.",
    }

@router.post("/request-otp")
async def request_otp(
    otp_request: OtpRequest,
    current_user: User = Depends(get_current_user_from_temp_token),
    db: Session = Depends(get_db)
):
    otp_code = ''.join(random.choices(string.digits, k=6))
    hashed_otp = get_password_hash(otp_code)

    existing_otp = get_otp_by_user_id(db, user_id=current_user.user_id, purpose=otp_request.purpose)
    if existing_otp:
        delete_otp(db, db_otp=existing_otp)

    create_otp(db, user_id=current_user.user_id, code=hashed_otp, purpose=otp_request.purpose)

    send_otp_email(to_email=current_user.email, otp=otp_code)

    return {"message": "OTP has been sent to your email."}

@router.post("/verify-otp", response_model=Token)
async def verify_otp(
    otp_data: OtpVerify,
    current_user: User = Depends(get_current_user_from_temp_token),
    db: Session = Depends(get_db)
):
    db_otp = get_otp_by_user_id(db, user_id=current_user.user_id, purpose=otp_data.purpose)

    if not db_otp or db_otp.is_used:
        raise HTTPException(status_code=400, detail="OTP not found or already used.")

    if datetime.datetime.now(datetime.timezone.utc) > db_otp.expires_at:
        delete_otp(db, db_otp)
        raise HTTPException(status_code=400, detail="OTP has expired.")

    if not verify_password(otp_data.code, db_otp.code):
        raise HTTPException(status_code=400, detail="Invalid OTP.")

    set_otp_as_used(db, db_otp)

    token_data = {"sub": current_user.email, "id": current_user.user_id}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/create", response_model=User)
async def create_new_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    user.password = get_password_hash(user.password)
    return create_user(db=db, user=user)


@router.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user