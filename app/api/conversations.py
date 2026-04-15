import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.schemas.conversation import (
    ConversationCreate,
    ConversationUpdate,
    ConversationResponse,
    ConversationListResponse,
    MessageCreate,
    MessageResponse,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


@router.get("", response_model=List[ConversationListResponse])
async def get_conversations(
    since: Optional[datetime] = Query(None, description="只返回自此时间以来更新的会话"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取用户的所有会话
    - 如果提供 since 参数，只返回 updated_at > since 的会话（增量同步）
    - 如果不提供 since 参数，返回所有会话（全量同步）
    """
    logger.info(f"[GET /conversations] user_id={current_user.id}, since={since}")
    query = select(Conversation).where(Conversation.user_id == current_user.id)

    if since:
        query = query.where(Conversation.updated_at > since)

    query = query.order_by(Conversation.is_pinned.desc(), Conversation.last_message_time.desc())

    result = await db.execute(query)
    conversations = result.scalars().all()

    response = []
    for conv in conversations:
        response.append(
            ConversationListResponse(
                id=conv.id,
                title=conv.title,
                is_pinned=conv.is_pinned,
                last_message_time=conv.last_message_time,
                last_message_preview=conv.last_message_preview,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=0,  # 不计算消息数量以提升性能
            )
        )
    return response


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"[POST /conversations] user_id={current_user.id}, title={data.title}")
    conversation = Conversation(
        user_id=current_user.id,
        title=data.title,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    logger.info(f"[POST /conversations] created conversation_id={conversation.id}")
    return conversation


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"[GET /conversations/{conversation_id}] user_id={current_user.id}")
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id
        )
        .options(selectinload(Conversation.messages))
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        logger.warning(f"[GET /conversations/{conversation_id}] Not found for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return conversation


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
        .options(selectinload(Conversation.messages))
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if data.title is not None:
        conversation.title = data.title
    if data.is_pinned is not None:
        conversation.is_pinned = data.is_pinned

    conversation.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(conversation)
    return conversation


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"[DELETE /conversations/{conversation_id}] user_id={current_user.id}")
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()

    if not conversation:
        logger.warning(f"[DELETE /conversations/{conversation_id}] Not found for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    await db.delete(conversation)
    await db.commit()
    return {"message": "Conversation deleted"}


@router.get("/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: str,
    since: Optional[datetime] = Query(None, description="只返回自此时间以来更新的消息"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取会话的消息
    - 如果提供 since 参数，只返回 updated_at > since 的消息（增量同步）
    - 如果不提供 since 参数，返回所有消息（全量同步）
    """
    # Verify conversation belongs to user
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    query = select(Message).where(Message.conversation_id == conversation_id)

    if since:
        query = query.where(Message.updated_at > since)

    query = query.order_by(Message.timestamp.asc())

    result = await db.execute(query)
    messages = result.scalars().all()
    return messages


@router.post("/{conversation_id}/messages", response_model=MessageResponse)
async def create_message(
    conversation_id: str,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify conversation belongs to user
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()

    # If conversation doesn't exist, auto-create it (handles temp chat IDs from client)
    if not conversation:
        logger.info(f"[POST /conversations/{conversation_id}/messages] Conversation not found, auto-creating")
        conversation = Conversation(
            id=conversation_id,
            user_id=current_user.id,
            title="新聊天",
        )
        db.add(conversation)
        await db.flush()  # Get the conversation ID without committing

    message = Message(
        conversation_id=conversation_id,
        type=data.type,
        content=data.content,
        media_path=data.media_path,
        is_from_me=True,
        reply_to_id=data.reply_to_id,
        reply_to_content=data.reply_to_content,
    )
    db.add(message)

    # Update conversation preview
    conversation.last_message_time = message.timestamp
    conversation.last_message_preview = data.content[:100] if data.content else f"[媒体]"
    conversation.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(message)
    return message


@router.patch("/{conversation_id}/messages/{message_id}/favorite")
async def toggle_favorite(
    conversation_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify conversation belongs to user
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    result = await db.execute(
        select(Message).where(
            Message.id == message_id, Message.conversation_id == conversation_id
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    message.is_favorite = not message.is_favorite
    message.updated_at = datetime.utcnow()

    await db.commit()
    return {"is_favorite": message.is_favorite}


@router.delete("/{conversation_id}/messages/{message_id}")
async def delete_message(
    conversation_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify conversation belongs to user
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    result = await db.execute(
        select(Message).where(
            Message.id == message_id, Message.conversation_id == conversation_id
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    await db.delete(message)
    await db.commit()
    return {"message": "Message deleted"}
