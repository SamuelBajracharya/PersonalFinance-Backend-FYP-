from fastapi import APIRouter, Depends, HTTPException, Response
from app.crud import (
    create_user,
    get_user_by_email,
    create_otp,
    get_otp_by_user_id,
    set_otp_as_used,
    delete_otp,
    update_user_verified_status,
    update_user_password,
)
from app.schemas import (
    User,
    UserCreate,
    TempToken,
    UserLogin,
    Token,
    OtpRequest,
    OtpVerify,
    PasswordResetRequest,
    ResetToken,
    PasswordReset,
)
from app.models.otp import OtpPurpose
from app.utils.deps import (
    get_current_user,
    get_db,
    get_current_user_from_temp_token,
    get_current_user_from_reset_token,
)
from sqlalchemy.orm import Session
from app.utils.auth import (
    create_temp_token,
    verify_password,
    create_access_token,
    create_refresh_token,
    get_password_hash,
)
from app.utils.email import send_otp_email
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

@router.post("/request-password-reset", response_model=TempToken)
async def request_password_reset(
    request: PasswordResetRequest, db: Session = Depends(get_db)
):
    user = get_user_by_email(db, email=request.email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User with this email does not exist.",
        )

    token_data = {"id": user.user_id, "token_type": "temp"}
    temp_token = create_temp_token(data=token_data)

    return {
        "temp_token": temp_token,
        "message": "User found. Please request an OTP for password reset.",
    }

@router.post("/request-otp")
async def request_otp(
    otp_request: OtpRequest,
    current_user: User = Depends(get_current_user_from_temp_token),
    db: Session = Depends(get_db)
):
    otp_code = ''.join(random.choices(string.digits, k=6))
    hashed_otp = get_password_hash(otp_code)

    # If existing OTP for same purpose, delete it first
    existing_otp = get_otp_by_user_id(db, user_id=current_user.user_id, purpose=otp_request.purpose)
    if existing_otp:
        delete_otp(db, db_otp=existing_otp)

    # Create new OTP
    create_otp(db, user_id=current_user.user_id, code=hashed_otp, purpose=otp_request.purpose)

    # 🧩 Pass purpose here
    send_otp_email(
        to_email=current_user.email,
        otp=otp_code,
        purpose=otp_request.purpose
    )

    return {"message": f"OTP for '{otp_request.purpose}' has been sent to your email."}


@router.post("/verify-otp")
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

    if otp_data.purpose == OtpPurpose.ACCOUNT_VERIFICATION:
        update_user_verified_status(db, user_id=current_user.user_id, is_verified=True)
        token_data = {"sub": current_user.email, "id": current_user.user_id}
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    if otp_data.purpose == OtpPurpose.PASSWORD_RESET:
        token_data = {"id": current_user.user_id, "token_type": "reset"}
        reset_token = create_temp_token(data=token_data)
        return ResetToken(
            reset_token=reset_token,
            message="OTP verified. Please reset your password.",
        )

    # Default case for other OTP purposes like TWO_FACTOR_AUTH
    token_data = {"sub": current_user.email, "id": current_user.user_id}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )

@router.post("/reset-password")
async def reset_password(
    password_data: PasswordReset,
    current_user: User = Depends(get_current_user_from_reset_token),
    db: Session = Depends(get_db),
):
    hashed_password = get_password_hash(password_data.new_password)
    update_user_password(db, user_id=current_user.user_id, new_password=hashed_password)
    return {"message": "Password has been reset successfully."}


@router.post("/create", response_model=TempToken)
async def create_new_user(user: UserCreate, db: Session = Depends(get_db)):
    db_user = get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user.password = get_password_hash(user.password)
    new_user = create_user(db=db, user=user)

    token_data = {"id": new_user.user_id, "token_type": "temp"}
    temp_token = create_temp_token(data=token_data)

    return {
        "temp_token": temp_token,
        "message": "User created. Please request an OTP to verify your account.",
    }


@router.get("/users/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user