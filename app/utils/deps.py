from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from app.utils.auth import decrypt_token
from app.db import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
temp_token_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/request-otp")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decrypt_token(token)
        if payload.get("token_type") == "temp":
            raise credentials_exception
        user_id = payload.get("id")
        if not user_id:
            raise credentials_exception

    except Exception as e:
        print("Token decryption failed:", str(e))
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_exception

    return user

async def get_current_user_from_temp_token(
    token: str = Depends(temp_token_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate temporary token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decrypt_token(token)
        if payload.get("token_type") != "temp":
            raise credentials_exception
        user_id = payload.get("id")
        if not user_id:
            raise credentials_exception

    except Exception as e:
        print("Temp token decryption failed:", str(e))
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_exception

    return user
