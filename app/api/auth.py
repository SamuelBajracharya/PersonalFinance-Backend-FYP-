from fastapi import APIRouter, Depends, HTTPException
from app.crud import create_user, get_user_by_email
from app.schemas import User, UserCreate, Token, UserLogin
from app.utils import get_current_user, get_password_hash, get_db
from sqlalchemy.orm import Session
from app.utils import (
    create_access_token,
    create_refresh_token,
    verify_password,
)

router = APIRouter()


@router.post("/login", response_model=Token)
async def login_user(user_login: UserLogin, db: Session = Depends(get_db)):
    user = get_user_by_email(db, email=user_login.email)
    if not user or not verify_password(user_login.password, user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Include both email and id in token payload
    token_data = {"sub": user.email, "id": user.id}

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
