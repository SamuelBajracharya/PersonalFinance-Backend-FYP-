from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer
from app.utils.auth import decrypt_token
from app.db import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


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
        # Decrypt JWE token using your jwcrypto-based helper
        payload = decrypt_token(token)

        # Expecting your login route encoded both id and email:
        # token_data = {"sub": user.email, "id": user.id}
        user_id = payload.get("id")
        if not user_id:
            raise credentials_exception

    except Exception as e:
        print("Token decryption failed:", str(e))  # helpful debug log
        raise credentials_exception

    # Fetch user by ID instead of email
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_exception

    return user
