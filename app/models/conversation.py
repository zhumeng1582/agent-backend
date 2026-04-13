from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False, default="新聊天")
    is_pinned = Column(Boolean, default=False)
    last_message_time = Column(DateTime, nullable=True)
    last_message_preview = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # For sync: last time user fetched this conversation
    last_synced_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(Integer, nullable=False, default=0)  # 0=text, 1=image, 2=voice, 3=video
    content = Column(Text, nullable=True)
    media_path = Column(Text, nullable=True)
    reasoning = Column(Text, nullable=True)
    is_from_me = Column(Boolean, nullable=False)
    is_favorite = Column(Boolean, default=False)
    translated_content = Column(Text, nullable=True)
    reply_to_id = Column(String, nullable=True)
    reply_to_content = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
