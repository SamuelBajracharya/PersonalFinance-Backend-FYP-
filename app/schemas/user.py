from pydantic import BaseModel
from datetime import datetime

class UserBase(BaseModel):
    email: str
    name: str

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class User(UserBase):
    user_id: str
    is_active: bool
    total_xp: int
    created_at: datetime

    class Config:
        from_attributes = True
