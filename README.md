# AI Usage Proxy Server

A proxy server that sits between users and Ollama, providing OpenAI-compatible API endpoints, token usage tracking per user, rate limiting, and admin controls.

## Architecture

```
Client (OpenAI SDK) ──> Proxy Server (Port 8000) ──> Ollama (Port 11434)
                              |
                              v
                        SQLite DB (Usage/Auth)
```

## Setup

### Prerequisites
- Python 3.10+
- Ollama installed and running
- At least one Ollama model pulled (e.g. `ollama pull llama3.2`)

### Installation

```bash
git clone <repo-url>
cd AI-Usage-Proxy-Server

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Server

You need two terminals:

**Terminal 1 - Ollama:**
```bash
ollama serve
```

**Terminal 2 - Proxy server (must be in venv):**
```bash
source venv/bin/activate
python main.py
```

The server starts at http://localhost:8000. The database (`db/proxy.db`) is created automatically on first run and persists across restarts.

### First-Time Setup

Create your first user via the admin API:
```bash
curl -X POST http://localhost:8000/admin/users -H "Authorization: Bearer admin-secret-key" -H "Content-Type: application/json" -d '{"user_id": "my-user"}'
```

Save the `api_key` from the response -- you need it for all user requests.

## Configuration

Settings via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `ADMIN_API_KEY` | `admin-secret-key` | Admin authentication key |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DATABASE_PATH` | `./db/proxy.db` | SQLite database file path |

## API Commands

### Public (no auth needed)

```bash
# Service status
curl http://localhost:8000/

# Health check
curl http://localhost:8000/health

# Swagger docs (open in browser)
# http://localhost:8000/docs
```

### User Endpoints

Require `Authorization: Bearer <api_key>` header.

```bash
# Chat completion (non-streaming)
curl http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer <api_key>" -d '{"model": "llama3.2", "messages": [{"role": "user", "content": "Hello"}]}'

# Chat completion (streaming - tokens appear in real time)
curl http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer <api_key>" -d '{"model": "llama3.2", "messages": [{"role": "user", "content": "Hello"}], "stream": true}'

# Vision model (image URL)
curl http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer <api_key>" -d '{"model": "moondream", "messages": [{"role": "user", "content": [{"type": "text", "text": "What is in this image?"}, {"type": "image_url", "image_url": {"url": "https://picsum.photos/200"}}]}]}'

# List available models
curl http://localhost:8000/v1/models -H "Authorization: Bearer <api_key>"

# Get your token usage
curl http://localhost:8000/v1/usage -H "Authorization: Bearer <api_key>"

# Get usage summary by model
curl http://localhost:8000/v1/usage/summary -H "Authorization: Bearer <api_key>"
```

### Admin Endpoints

Require `Authorization: Bearer <admin_api_key>` header.

```bash
# Create a user
curl -X POST http://localhost:8000/admin/users -H "Authorization: Bearer admin-secret-key" -H "Content-Type: application/json" -d '{"user_id": "user-123"}'

# List all users
curl http://localhost:8000/admin/users -H "Authorization: Bearer admin-secret-key"

# Get a specific user (includes API key)
curl http://localhost:8000/admin/users/user-123 -H "Authorization: Bearer admin-secret-key"

# Delete a specific user
curl -X DELETE http://localhost:8000/admin/users/user-123 -H "Authorization: Bearer admin-secret-key"

# Delete ALL users (clears users, usage records, and rate limits)
curl -X DELETE http://localhost:8000/admin/users -H "Authorization: Bearer admin-secret-key"

# Get a user's usage stats
curl http://localhost:8000/admin/users/user-123/usage -H "Authorization: Bearer admin-secret-key"

# Get a user's rate limits
curl http://localhost:8000/admin/users/user-123/limits -H "Authorization: Bearer admin-secret-key"

# Update a user's rate limits
curl -X PUT http://localhost:8000/admin/users/user-123/limits -H "Authorization: Bearer admin-secret-key" -H "Content-Type: application/json" -d '{"requests_per_minute": 10, "tokens_per_day": 50000, "total_token_limit": 1000000}'
```

### Rate Limit Fields

| Field | Default | Description |
|-------|---------|-------------|
| `requests_per_minute` | 60 | Max requests per minute |
| `requests_per_day` | 1000 | Max requests per day |
| `tokens_per_minute` | 100000 | Max tokens per minute |
| `tokens_per_day` | 1000000 | Max tokens per day |
| `total_token_limit` | unlimited | Lifetime token cap |

## Testing

All test commands require the venv to be active. Curl commands do not.

### Unit Tests (no Ollama needed)
```bash
pytest tests/test_basic.py -v
```

### Integration Tests (requires Ollama + running server)
```bash
SKIP_INTEGRATION_TESTS=false pytest tests/test_streaming.py tests/test_vision.py -v -s
```

### Load Testing (requires Ollama + running server)

Quick test (50 requests, 10 concurrent workers):
```bash
TEST_API_KEY=<api_key> python tests/test_load.py
```

Full load test with Locust web UI:
```bash
TEST_API_KEY=<api_key> locust -f tests/test_load.py --host=http://localhost:8000 --users=5 --spawn-rate=2
```

Optionally set the model (defaults to `llama3.2`):
```bash
TEST_API_KEY=<api_key> TEST_MODEL=llama3.2 python tests/test_load.py
```

Note: raise the rate limit before load testing to avoid 429 errors:
```bash
curl -X PUT http://localhost:8000/admin/users/<user_id>/limits -H "Authorization: Bearer admin-secret-key" -H "Content-Type: application/json" -d '{"requests_per_minute": 1000}'
```

## Database

Data is stored in `db/proxy.db` (SQLite) and persists across server restarts. Three tables:
- **users** - User IDs and API keys
- **usage** - Per-request token usage records (for auditing, rate limiting, billing)
- **rate_limits** - Per-user rate limit configuration

To start fresh, either delete `db/proxy.db` (requires server restart) or use the delete all users endpoint.

## Project Structure
```
AI-Usage-Proxy-Server/
├── main.py                      # FastAPI entry point
├── requirements.txt             # Dependencies
├── db/
│   └── proxy.db                 # SQLite database (auto-created, gitignored)
├── app/
│   ├── __init__.py
│   ├── config.py                # Settings (pydantic-settings)
│   ├── database.py              # SQLite + aiosqlite (users, usage, rate_limits)
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py              # API key authentication
│   │   └── rate_limit.py        # Sliding window rate limiting
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── completions.py       # /v1/chat/completions (streaming + non-streaming)
│   │   ├── admin.py             # Admin API (create users, set limits)
│   │   └── usage.py             # User usage tracking API
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ollama_client.py     # Ollama HTTP client (vision support)
│   │   └── token_tracker.py     # Token usage tracking
│   └── models/
│       ├── __init__.py
│       └── schemas.py           # Pydantic models (OpenAI-compatible)
└── tests/
    ├── __init__.py
    ├── test_basic.py            # Unit tests
    ├── test_streaming.py        # Streaming integration tests
    ├── test_vision.py           # Vision model tests
    └── test_load.py             # Load testing (locust)
```
