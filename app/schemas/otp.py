from pydantic import BaseModel
from app.models.otp import OtpPurpose

class OtpBase(BaseModel):
    purpose: OtpPurpose

class OtpRequest(OtpBase):
    pass

class OtpVerify(BaseModel):
    purpose: OtpPurpose
    code: str

class Otp(OtpBase):
    otp_id: str
    is_used: bool

    class Config:
        from_attributes = True
