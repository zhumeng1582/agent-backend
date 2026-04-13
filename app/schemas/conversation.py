from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class MessageBase(BaseModel):
    type: int = 0  # 0=text, 1=image, 2=voice, 3=video
    content: Optional[str] = None
    media_path: Optional[str] = None


class MessageCreate(MessageBase):
    reply_to_id: Optional[str] = None
    reply_to_content: Optional[str] = None


class MessageResponse(MessageBase):
    id: str
    conversation_id: str
    is_from_me: bool
    is_favorite: bool
    translated_content: Optional[str]
    reasoning: Optional[str]
    reply_to_id: Optional[str]
    reply_to_content: Optional[str]
    timestamp: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationBase(BaseModel):
    title: str = "新聊天"


class ConversationCreate(ConversationBase):
    pass


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    is_pinned: Optional[bool] = None


class ConversationResponse(ConversationBase):
    id: str
    is_pinned: bool
    last_message_time: Optional[datetime]
    last_message_preview: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: Optional[List[MessageResponse]] = None

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    id: str
    title: str
    is_pinned: bool
    last_message_time: Optional[datetime]
    last_message_preview: Optional[str]
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    class Config:
        from_attributes = True
