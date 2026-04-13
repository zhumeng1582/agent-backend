from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer
from datetime import datetime
import uuid

from app.core.database import Base


class AIProvider(Base):
    __tablename__ = "ai_providers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)  # e.g., "MiniMax", "OpenAI", "Ollama"
    provider_type = Column(String(50), nullable=False)  # e.g., "minimax", "openai", "ollama"
    api_key_encrypted = Column(Text, nullable=True)  # AES encrypted
    base_url = Column(Text, nullable=True)
    model_name = Column(String(100), nullable=False)  # e.g., "MiniMax-M2.7", "gpt-4"
    is_enabled = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    priority = Column(Integer, default=0)  # Lower = higher priority
    config = Column(Text, nullable=True)  # JSON for additional config
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
