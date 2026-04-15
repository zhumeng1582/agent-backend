from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.api import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Agent Backend API...")
    await init_db()

    # Log AI configuration status
    if settings.minimax_api_key:
        logger.info(f"[AI Config] MiniMax API Key: ****{settings.minimax_api_key[-4:]}")
        logger.info(f"[AI Config] MiniMax Base URL: {settings.minimax_base_url}")
        logger.info(f"[AI Config] MiniMax Model: {settings.minimax_model}")
    else:
        logger.warning("[AI Config] MiniMax API Key not configured in .env")

    if settings.openai_api_key:
        logger.info(f"[AI Config] OpenAI API Key: ****{settings.openai_api_key[-4:]}")
        logger.info(f"[AI Config] OpenAI Model: {settings.openai_model}")
    else:
        logger.warning("[AI Config] OpenAI API Key not configured in .env")

    if not settings.minimax_api_key and not settings.openai_api_key:
        logger.error("[AI Config] No AI provider configured! Set MINIMAX_API_KEY or OPENAI_API_KEY in .env")

    yield
    # Shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/")
async def root():
    return {"message": "Agent Backend API", "version": "1.0.0"}
