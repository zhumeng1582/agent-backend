import json
import base64
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import get_settings
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.models.ai_provider import AIProvider
from app.schemas.ai import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    AIProviderResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
    TranslationRequest,
    TranslationResponse,
    TTSRequest,
    TTSResponse,
)

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)
settings = get_settings()


async def get_default_provider(db: AsyncSession) -> Optional[AIProvider]:
    result = await db.execute(
        select(AIProvider).where(AIProvider.is_default == True, AIProvider.is_enabled == True)
    )
    return result.scalar_one_or_none()


async def get_provider_by_type(db: AsyncSession, provider_type: str) -> Optional[AIProvider]:
    result = await db.execute(
        select(AIProvider).where(
            AIProvider.provider_type == provider_type,
            AIProvider.is_enabled == True,
        ).order_by(AIProvider.priority.asc())
    )
    return result.scalar_one_or_none()


def decrypt_api_key(encrypted: str) -> str:
    # In production, use proper AES decryption
    # For now, this is a placeholder - the key should be encrypted at rest
    return encrypted


async def call_minimax_api(messages: List[dict], model: str, api_key: str, base_url: str = "https://api.minimaxi.com/v1") -> dict:
    logger.info(f"[call_minimax_api] Calling minimax API: model={model}, base_url={base_url}")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{base_url}/text/chatcompletion_v2",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": model,
                    "messages": messages,
                },
            )
            logger.info(f"[call_minimax_api] Response status: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"[call_minimax_api] Error response: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"AI API error: {response.text}",
                )
            return response.json()
    except Exception as e:
        logger.error(f"[call_minimax_api] Exception: {type(e).__name__}: {e}")
        raise


async def call_openai_api(messages: List[dict], model: str, api_key: str) -> dict:
    logger.info(f"[call_openai_api] Calling OpenAI API: model={model}")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": model,
                    "messages": messages,
                },
            )
            logger.info(f"[call_openai_api] Response status: {response.status_code}")
            if response.status_code != 200:
                logger.error(f"[call_openai_api] Error response: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"AI API error: {response.text}",
                )
            return response.json()
    except Exception as e:
        logger.error(f"[call_openai_api] Exception: {type(e).__name__}: {e}")
        raise


@router.get("/providers", response_model=List[AIProviderResponse])
async def get_providers(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AIProvider).where(AIProvider.is_enabled == True).order_by(AIProvider.priority.asc())
    )
    providers = result.scalars().all()
    return providers


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get provider
    provider = await get_default_provider(db)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No AI provider configured",
        )

    api_key = decrypt_api_key(provider.api_key_encrypted) if provider.api_key_encrypted else None
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider not properly configured",
        )

    messages = [msg.model_dump() for msg in request.messages]

    # Call appropriate provider
    if provider.provider_type == "minimax":
        result = await call_minimax_api(messages, request.model or provider.model_name, api_key, provider.base_url)
    elif provider.provider_type == "openai":
        result = await call_openai_api(messages, request.model or provider.model_name, api_key)
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Provider type {provider.provider_type} not supported",
        )

    # Parse response
    choices = result.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        reasoning = message.get("reasoning_content")
        usage = result.get("usage")
        return ChatResponse(
            content=content,
            reasoning=reasoning,
            model=request.model or provider.model_name,
            usage=usage,
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Invalid response from AI provider",
    )


@router.post("/chat/{conversation_id}", response_model=ChatResponse)
async def chat_in_conversation(
    conversation_id: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logger.info(f"[POST /ai/chat/{conversation_id}] user_id={current_user.id}, messages_count={len(request.messages)}")
    # Verify conversation belongs to user
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()

    # If conversation doesn't exist, auto-create it (handles temp chat IDs from client)
    if not conversation:
        logger.info(f"[POST /ai/chat/{conversation_id}] Conversation not found, auto-creating")
        conversation = Conversation(
            id=conversation_id,
            user_id=current_user.id,
            title="新聊天",
        )
        db.add(conversation)
        await db.flush()

    # Get provider from database, fallback to settings
    provider = await get_default_provider(db)

    # Determine which API to use
    api_key = None
    api_base_url = None
    api_model = None
    api_type = None

    if provider:
        api_key = decrypt_api_key(provider.api_key_encrypted) if provider.api_key_encrypted else None
        api_base_url = provider.base_url
        api_model = provider.model_name
        api_type = provider.provider_type
    elif settings.minimax_api_key:
        # Fallback to .env config
        api_key = settings.minimax_api_key
        api_base_url = settings.minimax_base_url
        api_model = settings.minimax_model
        api_type = "minimax"
        logger.info(f"[POST /ai/chat/{conversation_id}] Using MiniMax from settings")
    elif settings.openai_api_key:
        api_key = settings.openai_api_key
        api_base_url = None
        api_model = settings.openai_model
        api_type = "openai"
        logger.info(f"[POST /ai/chat/{conversation_id}] Using OpenAI from settings")

    if not api_key:
        logger.warning(f"[POST /ai/chat/{conversation_id}] No AI provider configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No AI provider configured. Please set MINIMAX_API_KEY or OPENAI_API_KEY in .env",
        )

    # Build messages with history
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.asc())
    )
    history_messages = history_result.scalars().all()

    messages = []
    for msg in history_messages:
        role = "user" if msg.is_from_me else "assistant"
        msg_content = msg.content or ""
        messages.append({"role": role, "content": msg_content})

    # Add new messages
    for new_msg in request.messages:
        messages.append(new_msg.model_dump())

    logger.info(f"[POST /ai/chat/{conversation_id}] Calling {api_type} provider with {len(messages)} messages, model={api_model}")
    logger.debug(f"[POST /ai/chat/{conversation_id}] Messages: {messages}")

    # Call provider
    if api_type == "minimax":
        result = await call_minimax_api(messages, request.model or api_model, api_key, api_base_url)
    elif api_type == "openai":
        result = await call_openai_api(messages, request.model or api_model, api_key)
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Provider type {api_type} not supported",
        )

    logger.info(f"[POST /ai/chat/{conversation_id}] Raw response: {result}")

    # Parse response
    choices = result.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        reasoning = message.get("reasoning_content")
        usage = result.get("usage")

        logger.info(f"[POST /ai/chat/{conversation_id}] AI response content length: {len(content) if content else 0}")

        # Save AI response to conversation
        ai_message = Message(
            conversation_id=conversation_id,
            type=0,
            content=content,
            reasoning=reasoning,
            is_from_me=False,
        )
        db.add(ai_message)
        await db.commit()

        return ChatResponse(
            content=content,
            reasoning=reasoning,
            model=request.model or api_model,
            usage=usage,
        )

    logger.warning(f"[POST /ai/chat/{conversation_id}] No choices in AI response, full response: {result}")
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Invalid response from AI provider",
    )


@router.post("/translate", response_model=TranslationResponse)
async def translate(
    request: TranslationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """翻译文本"""
    provider = await get_default_provider(db)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No AI provider configured",
        )

    api_key = decrypt_api_key(provider.api_key_encrypted) if provider.api_key_encrypted else None
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider not properly configured",
        )

    messages = [
        {"role": "user", "content": f"Translate the following text to {request.target_lang}. Only output the translation, nothing else.\n\nText: {request.text}"}
    ]

    if provider.provider_type == "minimax":
        result = await call_minimax_api(messages, request.model or provider.model_name, api_key, provider.base_url)
    elif provider.provider_type == "openai":
        result = await call_openai_api(messages, request.model or provider.model_name, api_key)
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Provider type {provider.provider_type} not supported",
        )

    choices = result.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        return TranslationResponse(translated_text=content.strip())

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Invalid response from AI provider",
    )


@router.post("/tts", response_class=Response)
async def text_to_speech(
    request: TTSRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """文本转语音"""
    provider = await get_provider_by_type(db, "minimax")
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS provider not configured",
        )

    api_key = decrypt_api_key(provider.api_key_encrypted) if provider.api_key_encrypted else None
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS provider not properly configured",
        )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{provider.base_url}/t2a_v2",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": request.model or settings.minimax_tts_model,
                "text": request.text,
                "stream": False,
                "voice_setting": {
                    "voice_id": request.voice_id or "female-tianmei",
                },
            },
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"TTS API error: {response.text}",
            )

        data = response.json()
        audio_data = data.get("data", {}).get("audio")
        if not audio_data:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No audio in response",
            )

        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_data)
        return Response(content=audio_bytes, media_type="audio/mp3")


@router.post("/image/generate", response_model=ImageGenerationResponse)
async def generate_image(
    request: ImageGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """生成图片"""
    provider = await get_provider_by_type(db, "minimax")
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image generation provider not configured",
        )

    api_key = decrypt_api_key(provider.api_key_encrypted) if provider.api_key_encrypted else None
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image generation provider not properly configured",
        )

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{provider.base_url}/image_generation",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": request.model or settings.minimax_image_model,
                "prompt": request.prompt,
                "aspect_ratio": request.aspect_ratio or "1:1",
                "response_format": "url",
                "n": 1,
                "prompt_optimizer": True,
            },
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Image generation API error: {response.text}",
            )

        data = response.json()
        image_urls = data.get("data", {}).get("image_urls", [])
        if not image_urls:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="No image URL in response",
            )

        return ImageGenerationResponse(image_url=image_urls[0])


@router.post("/image/describe")
async def describe_image(
    image_url: str,
    message: str = "请描述这张图片",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """描述图片内容"""
    provider = await get_default_provider(db)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No AI provider configured",
        )

    api_key = decrypt_api_key(provider.api_key_encrypted) if provider.api_key_encrypted else None
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider not properly configured",
        )

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": message},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        }
    ]

    if provider.provider_type == "minimax":
        result = await call_minimax_api(messages, provider.model_name, api_key, provider.base_url)
    elif provider.provider_type == "openai":
        result = await call_openai_api(messages, provider.model_name, api_key)
    else:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Provider type {provider.provider_type} not supported",
        )

    choices = result.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content", "")
        return {"description": content}

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Invalid response from AI provider",
    )
