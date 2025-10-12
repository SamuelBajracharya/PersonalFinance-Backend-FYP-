
from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

class TempToken(BaseModel):
    temp_token: str
    message: str

class OTPResponse(BaseModel):
    message: str

class OTPVerify(BaseModel):
    otp: str
