# AI Usage Proxy Server

## Implementation Status

All phases implemented. The server is fully functional with:
- OpenAI-compatible `/v1/chat/completions` endpoint (streaming + non-streaming)
- Vision support (base64 and URL images)
- API key authentication
- Sliding window rate limiting (requests/tokens per minute/day, total limit)
- Token usage tracking in SQLite
- Admin API for user/limit management
- Unit tests and integration tests

## Quick Start

```bash
pip install -r requirements.txt
python main.py
# Server runs on http://localhost:8000
# Ollama must be running on http://localhost:11434
```

## Running Tests

```bash
# Unit tests (no Ollama needed)
pytest tests/test_basic.py -v

# Integration tests (requires Ollama + running server)
SKIP_INTEGRATION_TESTS=false pytest tests/test_streaming.py tests/test_vision.py -v -s

# Load test
python tests/test_load.py
# or with locust:
locust -f tests/test_load.py --host=http://localhost:8000
```

## Architecture

```
Client (OpenAI SDK) ──▶ Proxy Server (Port 8000) ──▶ Ollama (Port 11434)
                              │
                              ▼
                        SQLite DB (Usage/Auth)
```

## Tech Stack
- **FastAPI**: Async web framework
- **httpx**: Async HTTP client for forwarding requests to Ollama
- **SQLite + aiosqlite**: Lightweight async database for usage tracking
- **Pydantic**: Request/response validation

## Project Structure
```
AI-Usage-Proxy-Server/
├── main.py                      # FastAPI entry point
├── requirements.txt             # Dependencies
├── app/
│   ├── __init__.py
│   ├── config.py                # Settings (pydantic-settings)
│   ├── database.py              # SQLite + aiosqlite (users, usage, rate_limits)
│   ├── middleware/
│   │   ├── auth.py              # API key authentication
│   │   └── rate_limit.py        # Sliding window rate limiting
│   ├── routers/
│   │   ├── completions.py       # /v1/chat/completions (streaming + non-streaming)
│   │   ├── admin.py             # Admin API (create users, set limits)
│   │   └── usage.py             # User usage tracking API
│   ├── services/
│   │   ├── ollama_client.py     # Ollama HTTP client (vision support)
│   │   └── token_tracker.py     # Token usage tracking
│   └── models/
│       └── schemas.py           # Pydantic models (OpenAI-compatible)
└── tests/
    ├── test_basic.py            # Unit tests
    ├── test_streaming.py        # Streaming integration tests
    ├── test_vision.py           # Vision model tests
    └── test_load.py             # Load testing (locust)
```

## API Endpoints

### User endpoints (require `Authorization: Bearer <api_key>`)
- `POST /v1/chat/completions` - Chat completion (streaming + non-streaming)
- `GET /v1/models` - List available models
- `GET /v1/usage` - Get your token usage
- `GET /v1/usage/summary` - Usage aggregated by model

### Admin endpoints (require `Authorization: Bearer <admin_api_key>`)
- `POST /admin/users` - Create user
- `GET /admin/users` - List all users
- `GET /admin/users/{user_id}` - Get user details
- `DELETE /admin/users/{user_id}` - Delete user
- `GET /admin/users/{user_id}/usage` - Get user's usage stats
- `GET /admin/users/{user_id}/limits` - Get user's rate limits
- `PUT /admin/users/{user_id}/limits` - Update user's rate limits

### Public endpoints
- `GET /` - Service status
- `GET /health` - Health check

## Configuration

Settings via environment variables or `.env` file:
- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `ADMIN_API_KEY` (default: `admin-secret-key`)
- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8000`)
- `DATABASE_PATH` (default: `./proxy.db`)

## Database Schema

Three tables: `users` (TEXT PK), `usage` (per-request records), `rate_limits` (per-user limits).

## Key Design Decisions

1. **SSE streaming**: Matches OpenAI API format, compatible with existing SDKs
2. **TEXT primary key for users**: Self-documenting IDs, URL-safe, compatible with external systems
3. **Per-request usage records**: Enables auditing, rate limiting, and billing
4. **Sliding window rate limiting**: In-memory for fast checks + DB for persistence. No boundary exploit (unlike fixed window)
5. **API key format**: `sk-{user_id}-{random}` - extractable user_id without DB lookup
6. **Separate admin auth**: Config-based admin secret, prevents regular users from accessing admin functions
