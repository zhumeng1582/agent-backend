from datetime import datetime, timedelta
import random
import string
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import redis

from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from app.core.config import get_settings
from app.core.aliyun_notification import aliyun_notification
from app.models.user import User, RefreshToken, SMSCode, UserOAuth
from app.schemas.user import (
    UserCreate,
    UserResponse,
    Token,
    TokenRefresh,
    LoginRequest,
    PhoneLoginRequest,
    PhoneSendCodeRequest,
    PhoneVerifyRequest,
    PhoneRegisterRequest,
    WechatLoginRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    PasswordChangeRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# Redis client for SMS codes
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def generate_sms_code() -> str:
    """Generate 6-digit SMS code"""
    return ''.join(random.choices(string.digits, k=6))


def store_sms_code(phone: str, code: str) -> None:
    """Store SMS code in Redis with 5 min expiry"""
    key = f"sms_code:{phone}"
    redis_client.setex(key, 300, code)  # 5 minutes expiry


def verify_sms_code(phone: str, code: str) -> bool:
    """Verify SMS code from Redis"""
    key = f"sms_code:{phone}"
    stored_code = redis_client.get(key)
    if stored_code and stored_code == code:
        redis_client.delete(key)  # Code used, delete it
        return True
    return False


def store_reset_code(identifier: str, code: str) -> None:
    """Store password reset code in Redis with 10 min expiry"""
    key = f"password_reset:{identifier}"
    redis_client.setex(key, 600, code)  # 10 minutes expiry


def verify_reset_code(identifier: str, code: str) -> bool:
    """Verify password reset code from Redis"""
    key = f"password_reset:{identifier}"
    stored_code = redis_client.get(key)
    if stored_code and stored_code == code:
        redis_client.delete(key)  # Code used, delete it
        return True
    return False


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    # Check if email or phone exists
    if user_data.email:
        result = await db.execute(select(User).where(User.email == user_data.email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )

    # Create user
    user = User(
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password) if user_data.password else None,
        nickname=user_data.nickname,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Create tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    # Store refresh token
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/phone/send")
async def send_sms_code(
    request: PhoneSendCodeRequest,
    background_tasks: BackgroundTasks,
):
    """Send SMS verification code to phone number"""
    code = "123456"  # TODO: Use Aliyun SMS in production
    store_sms_code(request.phone, code)
    print(f"[SMS] Code for {request.phone}: {code}")

    return {"message": "Verification code sent", "code": code}


@router.post("/phone/register", response_model=UserResponse)
async def phone_register(
    request: PhoneRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    # Check if phone exists
    result = await db.execute(select(User).where(User.phone == request.phone))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already registered",
        )

    # Create user
    user = User(
        phone=request.phone,
        phone_password_hash=get_password_hash(request.password) if request.password else None,
        nickname=request.nickname,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/phone/login", response_model=Token)
async def phone_login(
    request: PhoneLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.phone == request.phone))
    user = result.scalar_one_or_none()

    if not user or not user.phone_password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phone number not registered or no password set",
        )

    if not verify_password(request.password, user.phone_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Create tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    # Store refresh token
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/phone/verify", response_model=Token)
async def phone_verify(
    request: PhoneVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    # Verify SMS code
    if not verify_sms_code(request.phone, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    # Find or create user
    result = await db.execute(select(User).where(User.phone == request.phone))
    user = result.scalar_one_or_none()

    if not user:
        # Create new user
        user = User(phone=request.phone)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Create tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    # Store refresh token
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/wechat/login", response_model=Token)
async def wechat_login(
    request: WechatLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    # TODO: Exchange WeChat code for session_key/openid
    # This requires calling WeChat API:
    # https://api.weixin.qq.com/sns/jscode2session?appid=APPID&secret=SECRET&js_code=CODE&grant_type=authorization_code

    # For now, simulate the response
    # In production, replace with actual WeChat API call
    wechat_openid = f"wechat_{request.code}"  # Simulated

    # Check if OAuth account exists
    result = await db.execute(
        select(UserOAuth).where(
            UserOAuth.provider == "wechat",
            UserOAuth.provider_user_id == wechat_openid,
        )
    )
    oauth_account = result.scalar_one_or_none()

    if oauth_account:
        # Get user
        result = await db.execute(select(User).where(User.id == oauth_account.user_id))
        user = result.scalar_one_or_none()
    else:
        # Create new user with OAuth account
        user = User(nickname=f"微信用户_{wechat_openid[-4:]}")
        db.add(user)
        await db.flush()

        oauth_account = UserOAuth(
            user_id=user.id,
            provider="wechat",
            provider_user_id=wechat_openid,
        )
        db.add(oauth_account)
        await db.commit()
        await db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Create tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    # Store refresh token
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/apple/login", response_model=Token)
async def apple_login(
    id_token: str,  # Apple ID token from client
    db: AsyncSession = Depends(get_db),
):
    # TODO: Verify Apple ID token with Apple
    # Apple provides id_token which contains user's Apple ID

    # For now, use the id_token as the user identifier
    apple_user_id = f"apple_{id_token[:16]}"

    # Check if OAuth account exists
    result = await db.execute(
        select(UserOAuth).where(
            UserOAuth.provider == "apple",
            UserOAuth.provider_user_id == apple_user_id,
        )
    )
    oauth_account = result.scalar_one_or_none()

    if oauth_account:
        result = await db.execute(select(User).where(User.id == oauth_account.user_id))
        user = result.scalar_one_or_none()
    else:
        # Create new user with OAuth account
        user = User(nickname=f"Apple用户")
        db.add(user)
        await db.flush()

        oauth_account = UserOAuth(
            user_id=user.id,
            provider="apple",
            provider_user_id=apple_user_id,
        )
        db.add(oauth_account)
        await db.commit()
        await db.refresh(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    # Create tokens
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(data={"sub": user.id})

    # Store refresh token
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    db_refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token,
        expires_at=expires_at,
    )
    db.add(db_refresh_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh_token(token_data: TokenRefresh, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(token_data.refresh_token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")

    # Check if token exists and not revoked
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == token_data.refresh_token,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked == False,
        )
    )
    db_token = result.scalar_one_or_none()

    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found or revoked",
        )

    if db_token.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    # Revoke old token
    db_token.revoked = True

    # Create new tokens
    access_token = create_access_token(data={"sub": user_id})
    new_refresh_token = create_refresh_token(data={"sub": user_id})

    # Store new refresh token
    expires_at = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    new_db_refresh_token = RefreshToken(
        user_id=user_id,
        token=new_refresh_token,
        expires_at=expires_at,
    )
    db.add(new_db_refresh_token)
    await db.commit()

    return Token(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(
    token_data: TokenRefresh,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Revoke refresh token
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == token_data.refresh_token,
            RefreshToken.user_id == current_user.id,
        )
    )
    db_token = result.scalar_one_or_none()
    if db_token:
        db_token.revoked = True
        await db.commit()

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/phone/bind")
async def bind_phone(
    request: PhoneVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bind phone number to existing user account"""
    # Verify SMS code
    if not verify_sms_code(request.phone, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    # Check if phone already bound to another user
    result = await db.execute(select(User).where(User.phone == request.phone))
    existing_user = result.scalar_one_or_none()
    if existing_user and existing_user.id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number already bound to another account",
        )

    # Bind phone to user
    current_user.phone = request.phone
    await db.commit()

    return {"message": "Phone bound successfully"}


@router.post("/phone/password")
async def set_phone_password(
    phone: str,
    password: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set password for phone login"""
    if current_user.phone != phone:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phone number does not match current user",
        )

    current_user.phone_password_hash = get_password_hash(password)
    await db.commit()

    return {"message": "Password set successfully"}


@router.post("/password/forgot")
async def forgot_password(
    request: PasswordForgotRequest,
    background_tasks: BackgroundTasks,
):
    """Send password reset code via email or SMS"""
    if not request.email and not request.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or phone is required",
        )

    # Find user by email or phone
    user = None
    identifier = None

    if request.email:
        result = await db.execute(select(User).where(User.email == request.email))
        user = result.scalar_one_or_none()
        identifier = request.email

    if not user and request.phone:
        result = await db.execute(select(User).where(User.phone == request.phone))
        user = result.scalar_one_or_none()
        identifier = request.phone

    if not user:
        # Don't reveal that user doesn't exist for security
        return {"message": "If the account exists, a reset code has been sent"}

    # Generate and store reset code
    code = "123456"  # TODO: Use Aliyun SMS/Email in production
    store_reset_code(identifier, code)
    print(f"[Password Reset] Code for {identifier}: {code}")

    return {"message": "If the account exists, a reset code has been sent"}


@router.post("/password/reset")
async def reset_password(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Reset password with verification code"""
    if not request.email and not request.phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email or phone is required",
        )

    identifier = request.email or request.phone

    # Verify reset code
    if not verify_reset_code(identifier, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code",
        )

    # Find user
    user = None
    if request.email:
        result = await db.execute(select(User).where(User.email == request.email))
        user = result.scalar_one_or_none()

    if not user and request.phone:
        result = await db.execute(select(User).where(User.phone == request.phone))
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update password
    user.hashed_password = get_password_hash(request.new_password)
    user.phone_password_hash = get_password_hash(request.new_password)
    await db.commit()

    return {"message": "Password reset successfully"}


@router.post("/password/change")
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change password for logged-in user"""
    # Check if user has a password set
    if not current_user.hashed_password and not current_user.phone_password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No password set for this account",
        )

    # Verify old password
    old_password_hash = current_user.hashed_password or current_user.phone_password_hash
    if not verify_password(request.old_password, old_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
        )

    # Update password
    new_hash = get_password_hash(request.new_password)
    current_user.hashed_password = new_hash
    current_user.phone_password_hash = new_hash
    await db.commit()

    return {"message": "Password changed successfully"}
