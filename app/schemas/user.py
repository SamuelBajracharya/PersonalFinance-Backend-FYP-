from pydantic import BaseModel, EmailStr
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr
    name: str

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    new_password: str

class User(UserBase):
    user_id: str
    is_active: bool
    is_verified: bool
    total_xp: int
    savings: int
    goals_completed: int
    rank: str
    created_at: datetime

    class Config:
        from_attributes = True