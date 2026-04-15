from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserUsage

router = APIRouter(prefix="/usage", tags=["usage"])


class UsageResponse(BaseModel):
    chat_count: int
    tokens_used: int
    remaining: int
    limit: int


class UsageUpdate(BaseModel):
    chat_count: int = 0
    tokens_used: int = 0


@router.get("", response_model=UsageResponse)
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's usage stats for today"""
    today_start = UserUsage.get_today_start()

    result = await db.execute(
        select(UserUsage).where(
            and_(
                UserUsage.user_id == current_user.id,
                UserUsage.date >= today_start,
            )
        )
    )
    usage = result.scalar_one_or_none()

    if not usage:
        # Return default values if no usage record exists
        return UsageResponse(
            chat_count=0,
            tokens_used=0,
            remaining=100,
            limit=100,
        )

    remaining = max(0, 100 - usage.chat_count)
    return UsageResponse(
        chat_count=usage.chat_count,
        tokens_used=usage.tokens_used,
        remaining=remaining,
        limit=100,
    )


@router.post("", response_model=UsageResponse)
async def update_usage(
    update: UsageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user's usage stats (called by AI chat endpoints)"""
    today_start = UserUsage.get_today_start()

    result = await db.execute(
        select(UserUsage).where(
            and_(
                UserUsage.user_id == current_user.id,
                UserUsage.date >= today_start,
            )
        )
    )
    usage = result.scalar_one_or_none()

    if not usage:
        # Create new usage record
        usage = UserUsage(
            user_id=current_user.id,
            date=today_start,
            chat_count=update.chat_count,
            tokens_used=update.tokens_used,
        )
        db.add(usage)
    else:
        # Update existing record
        usage.chat_count += update.chat_count
        usage.tokens_used += update.tokens_used

    await db.commit()
    await db.refresh(usage)

    remaining = max(0, 100 - usage.chat_count)
    return UsageResponse(
        chat_count=usage.chat_count,
        tokens_used=usage.tokens_used,
        remaining=remaining,
        limit=100,
    )
