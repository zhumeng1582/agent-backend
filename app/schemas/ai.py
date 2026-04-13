from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ChatMessage(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None  # If not specified, use default provider
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048


class ChatResponse(BaseModel):
    content: str
    reasoning: Optional[str] = None
    model: str
    usage: Optional[Dict[str, Any]] = None


class AIProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    model_name: str
    is_enabled: bool
    is_default: bool

    class Config:
        from_attributes = True


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: Optional[str] = None
    aspect_ratio: Optional[str] = "1:1"
    quality: Optional[str] = "standard"


class ImageGenerationResponse(BaseModel):
    image_url: str
    revised_prompt: Optional[str] = None


class TranslationRequest(BaseModel):
    text: str
    target_lang: str = "Chinese"
    model: Optional[str] = None


class TranslationResponse(BaseModel):
    translated_text: str


class TTSRequest(BaseModel):
    text: str
    model: Optional[str] = None
    voice_id: Optional[str] = "female-tianmei"


class TTSResponse(BaseModel):
    audio_url: str
