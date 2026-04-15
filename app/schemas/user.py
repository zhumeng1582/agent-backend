from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: Optional[str] = None
    nickname: Optional[str] = None


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(UserBase):
    id: str
    nickname: Optional[str]
    avatar_url: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PhoneLoginRequest(BaseModel):
    phone: str
    password: str


class PhoneSendCodeRequest(BaseModel):
    phone: str


class PhoneVerifyRequest(BaseModel):
    phone: str
    code: str


class PhoneRegisterRequest(BaseModel):
    phone: str
    password: Optional[str] = None
    nickname: Optional[str] = None


class WechatLoginRequest(BaseModel):
    code: str  # WeChat OAuth2 authorization code


class PasswordForgotRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    code: str
    new_password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str
