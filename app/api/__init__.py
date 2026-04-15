from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router
from app.api.ai import router as ai_router
from app.api.usage import router as usage_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(conversations_router)
api_router.include_router(ai_router)
api_router.include_router(usage_router)
