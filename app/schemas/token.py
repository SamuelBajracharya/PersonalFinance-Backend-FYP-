
from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class TokenData(BaseModel):
    email: Optional[str] = None

class TempToken(BaseModel):
    temp_token: str
    message: str

class ResetToken(BaseModel):
    reset_token: str
    message: str
