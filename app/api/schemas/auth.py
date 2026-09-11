from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, Field


from app.api.models.enum import UserType
from app.api.models.enum import OtpStatus


class AuthBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class TokenData(AuthBase):
    email: str
    user_type: UserType


class Token(AuthBase):
    access_token: str
    token_type: str = "bearer"


class EmailVerify(AuthBase):
    email: str
    otp_code: str


class ResendOtp(AuthBase):
    email: str


class EmailLogin(AuthBase):
    email: EmailStr
    password: str = Field(..., min_length=8)


class UserSignUp(EmailLogin):
    first_name: str
    last_name: str


class OtpInDB(AuthBase):
    otp: str
    user_id: UUID
    status: OtpStatus = "valid"
    expires_at: datetime


class SignUpResponse(BaseModel):
    pass


class OtpResendResponse(BaseModel):
    pass


class LogoutResponse(BaseModel):
    pass
