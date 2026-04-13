# Agent Backend

FastAPI backend for the Agent chat application.

## Features

- User authentication (JWT) - Email, Phone, WeChat, Apple
- Conversation & message management
- AI provider proxy (MiniMax, OpenAI, etc.)
- Multi-device sync
- File storage (S3/MinIO)

## Quick Start

### 1. Start infrastructure

```bash
docker-compose up -d
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. API Documentation

Open http://localhost:8000/docs for Swagger UI.

## API Endpoints

### Auth
- `POST /api/v1/auth/register` - Email registration
- `POST /api/v1/auth/login` - Email + password login
- `POST /api/v1/auth/phone/send` - Send SMS verification code
- `POST /api/v1/auth/phone/register` - Phone registration
- `POST /api/v1/auth/phone/login` - Phone + password login
- `POST /api/v1/auth/phone/verify` - Phone + SMS code login
- `POST /api/v1/auth/phone/bind` - Bind phone to account
- `POST /api/v1/auth/phone/password` - Set phone password
- `POST /api/v1/auth/wechat/login` - WeChat login
- `POST /api/v1/auth/apple/login` - Apple login
- `POST /api/v1/auth/refresh` - Refresh token
- `POST /api/v1/auth/logout` - Logout
- `GET /api/v1/auth/me` - Current user

### Conversations
- `GET /api/v1/conversations` - List conversations
- `POST /api/v1/conversations` - Create conversation
- `GET /api/v1/conversations/{id}` - Get conversation
- `PATCH /api/v1/conversations/{id}` - Update conversation
- `DELETE /api/v1/conversations/{id}` - Delete conversation

### Messages
- `GET /api/v1/conversations/{id}/messages` - Get messages
- `POST /api/v1/conversations/{id}/messages` - Create message
- `PATCH /api/v1/conversations/{id}/messages/{msg_id}/favorite` - Toggle favorite
- `DELETE /api/v1/conversations/{id}/messages/{msg_id}` - Delete message

### AI
- `GET /api/v1/ai/providers` - List AI providers
- `POST /api/v1/ai/chat` - Chat (stateless)
- `POST /api/v1/ai/chat/{conversation_id}` - Chat in conversation

## Docker Deployment

```bash
# Build
docker build -t agent-backend .

# Run
docker run -d -p 8000:8000 --env-file .env agent-backend
```

## Database Tables

- `users` - User accounts
- `refresh_tokens` - JWT refresh tokens
- `user_oauth` - OAuth accounts (WeChat, Apple, etc.)
- `sms_codes` - SMS verification codes (in Redis)
- `conversations` - Chat conversations
- `messages` - Chat messages
- `ai_providers` - AI provider configurations
