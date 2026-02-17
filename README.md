# AI Usage Proxy Server

This system is a proxy server between users and Ollama that provides chat response and vision processing. Some features include OpenAI-compatible API endpoints, per-user token tracking, rate limiting, billing, and admin controls. Clients use the standard OpenAI SDK — they point at the proxy instead of OpenAI's API. A demo UI for chat, usage viewing, and administration is also included!

## Architecture

```
Client (OpenAI SDK) ──> Proxy Server (Port 8000) ──> Ollama (Port 11434)
                              │
                              v
                        SQLite DB (Usage/Auth/Billing)
```

## Setup

### Prerequisites
- Python 3.10+
- Ollama installed and running
- At least one Ollama model pulled (e.g. `ollama pull llama3.2`)

### Installation

```bash
git clone https://github.com/hirolemo/AI-Usage-Proxy-Server
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

Or if you'd like, you can also specify the number of parallel connections to get concurrent completions (more connections may slow down each completion and requires higher GPU usage):
```bash
OLLAMA_NUM_PARALLEL=3 ollama serve
```


**Terminal 2 - Proxy server (must be in venv):**
```bash
source venv/bin/activate
python main.py
```

The server starts at http://localhost:8000. The demo UI is at http://localhost:8000/static/index.html. The database (`db/proxy.db`) is created automatically on first run and persists across restarts.

### First-Time Setup

You can create your first user via the UI on the admin page: http://localhost:8000/static/index.html (`admin-secret-key` is the admin API key), or in a terminal via the admin API:
```bash
curl -X POST http://localhost:8000/admin/users -H "Authorization: Bearer admin-secret-key" -H "Content-Type: application/json" -d '{"user_id": "my-user"}'
```

Save the user's `api_key` from the response - you'll need it for all user requests. You can also view all user keys in the UI's admin panel and use the site from here on out, or continue with `curl`-based terminal API calls via the examples below. For the sake of the demo, there's only 1 admin key (`admin-secret-key`), since multiple admins would offer the same functionality.

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
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api_key>" \
  -d '{"model": "llama3.2:1b", "messages": [{"role": "user", "content": "Hello"}]}'

# Chat completion (streaming - tokens appear in real time)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api_key>" \
  -d '{"model": "llama3.2:1b", "messages": [{"role": "user", "content": "Hello"}], "stream": true}'

# Chat completion with JSON response format
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api_key>" \
  -d '{"model": "llama3.2:1b", "messages": [{"role": "user", "content": "Return a JSON object with a greeting field"}], "response_format": {"type": "json_object"}}'

# Vision model (image URL)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api_key>" \
  -d '{"model": "moondream", "messages": [{"role": "user", "content": [{"type": "text", "text": "What is in this image?"}, {"type": "image_url", "image_url": {"url": "https://picsum.photos/200"}}]}]}'

# Image file upload (multipart form data)
curl -X POST http://localhost:8000/v1/chat/completions/upload \
  -H "Authorization: Bearer <api_key>" \
  -F "model=moondream" \
  -F 'messages=[{"role":"user","content":"What is in this image?"}]' \
  -F "files=@photo.jpg"

# List available models
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer <api_key>"

# Get your token usage
curl http://localhost:8000/v1/usage \
  -H "Authorization: Bearer <api_key>"

# Get usage summary by model
curl http://localhost:8000/v1/usage/summary \
  -H "Authorization: Bearer <api_key>"

# Get paginated request history
curl "http://localhost:8000/v1/usage/history?limit=20&offset=0" \
  -H "Authorization: Bearer <api_key>"

# Get current model pricing
curl http://localhost:8000/v1/pricing \
  -H "Authorization: Bearer <api_key>"
```

### Admin Endpoints

Require `Authorization: Bearer <admin_api_key>` header.

#### User Management

```bash
# Create a user
curl -X POST http://localhost:8000/admin/users \
  -H "Authorization: Bearer admin-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-123"}'

# List all users
curl http://localhost:8000/admin/users \
  -H "Authorization: Bearer admin-secret-key"

# Get a specific user (includes API key)
curl http://localhost:8000/admin/users/user-123 \
  -H "Authorization: Bearer admin-secret-key"

# Delete a specific user
curl -X DELETE http://localhost:8000/admin/users/user-123 \
  -H "Authorization: Bearer admin-secret-key"

# Delete ALL users (clears users, usage records, and rate limits)
curl -X DELETE http://localhost:8000/admin/users \
  -H "Authorization: Bearer admin-secret-key"
```

#### Usage & Rate Limits

```bash
# Get a user's usage stats (includes cost)
curl http://localhost:8000/admin/users/user-123/usage \
  -H "Authorization: Bearer admin-secret-key"

# Get a user's rate limits
curl http://localhost:8000/admin/users/user-123/limits \
  -H "Authorization: Bearer admin-secret-key"

# Update a user's rate limits
curl -X PUT http://localhost:8000/admin/users/user-123/limits \
  -H "Authorization: Bearer admin-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"requests_per_minute": 10, "tokens_per_day": 50000, "total_token_limit": 1000000}'
```

#### Pricing Management

```bash
# Set pricing for a model
curl -X POST http://localhost:8000/admin/pricing \
  -H "Authorization: Bearer admin-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2:1b", "input_cost_per_million": 0.15, "output_cost_per_million": 0.60}'

# List all model pricing
curl http://localhost:8000/admin/pricing \
  -H "Authorization: Bearer admin-secret-key"

# Get pricing for a specific model
curl http://localhost:8000/admin/pricing/llama3.2:1b \
  -H "Authorization: Bearer admin-secret-key"

# Update pricing for a model
curl -X PUT http://localhost:8000/admin/pricing/llama3.2:1b \
  -H "Authorization: Bearer admin-secret-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2:1b", "input_cost_per_million": 0.20, "output_cost_per_million": 0.80}'

# Delete pricing for a model
curl -X DELETE http://localhost:8000/admin/pricing/llama3.2:1b \
  -H "Authorization: Bearer admin-secret-key"

# Get pricing change history (all models)
curl http://localhost:8000/admin/pricing/history/all \
  -H "Authorization: Bearer admin-secret-key"

# Get pricing change history for a specific model
curl http://localhost:8000/admin/pricing/history/llama3.2:1b \
  -H "Authorization: Bearer admin-secret-key"
```

### Rate Limit Fields

| Field | Default | Description |
|-------|---------|-------------|
| `requests_per_minute` | 60 | Max requests per minute |
| `requests_per_day` | 1000 | Max requests per day |
| `tokens_per_minute` | 100000 | Max tokens per minute |
| `tokens_per_day` | 1000000 | Max tokens per day |
| `total_token_limit` | unlimited | Lifetime token cap |

## Configuration

Settings via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MAX_CONCURRENT` | `1` | Max concurrent requests to Ollama |
| `ADMIN_API_KEY` | `admin-secret-key` | Admin authentication key |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DATABASE_PATH` | `./db/proxy.db` | SQLite database file path |
| `MAX_UPLOAD_SIZE_MB` | `10` | Max image upload size in MB |
| `ALLOWED_IMAGE_TYPES` | `jpeg, png, gif, webp` | Accepted image MIME types |

In app/config.py:10, the Pydantic Settings class is configured with env_file=".env". I wanted to allow support for 
loading configs from a .env file, but made it optional. If the file doesn't exist, Pydantic 
simply ignores it and falls back to actual environment variables or defaults.                         
                                                                                                      
To accomplish this, you can create a .env file with the following contents:                                              
```
OLLAMA_BASE_URL=http://localhost:11434
ADMIN_API_KEY=my-secret
PORT=9000
```

## Testing

All test commands require the venv to be active. Curl commands do not.

### Unit Tests (no Ollama needed)
```bash
pytest tests/test_basic.py -v
```

### Integration Tests (requires Ollama + running server)
```bash
pytest tests/test_streaming.py tests/test_vision.py -v -s
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

Data is stored in `db/proxy.db` (SQLite) and persists across server restarts. Five tables:
- **users** — User IDs and API keys
- **usage** — Per-request token usage records (tokens, cost, request_id, prompt preview)
- **rate_limits** — Per-user rate limit configuration
- **model_pricing** — Per-model input/output cost rates
- **pricing_history** — Append-only audit log of pricing changes

To start fresh, either delete `db/proxy.db` (requires server restart) or use the delete all users endpoint.

## Project Structure

```
AI-Usage-Proxy-Server/
├── main.py                      # FastAPI entry point, middleware stack, static mount
├── requirements.txt             # Dependencies
├── mock_ollama.py               # Instant-response Ollama mock for load testing
├── db/
│   └── proxy.db                 # SQLite database (auto-created, gitignored)
├── app/
│   ├── config.py                # Settings (pydantic-settings, env vars)
│   ├── database.py              # SQLite + aiosqlite, connection pool, all queries
│   ├── middleware/
│   │   ├── auth.py              # API key authentication middleware
│   │   ├── rate_limit.py        # Sliding window rate limiter
│   │   └── request_id.py        # X-Request-Id middleware
│   ├── routers/
│   │   ├── completions.py       # /v1/chat/completions + /upload, shared handler
│   │   ├── admin.py             # User CRUD, rate limits, pricing CRUD
│   │   └── usage.py             # User usage, history, pricing read
│   ├── services/
│   │   ├── ollama_client.py     # Async Ollama HTTP client, OpenAI↔Ollama transforms
│   │   └── token_tracker.py     # Token + cost tracking, streaming wrapper
│   └── models/
│       └── schemas.py           # Pydantic models (OpenAI-compatible)
├── static/
│   ├── index.html               # Demo UI layout
│   ├── app.js                   # API calls, state management, DOM logic
│   └── style.css                # Styling, responsive design
└── tests/
    ├── test_basic.py            # Unit tests (mocked Ollama)
    ├── test_streaming.py        # Streaming integration tests (OpenAI SDK)
    ├── test_vision.py           # Vision model tests (OpenAI SDK)
    └── test_load.py             # Load testing (standalone + locust)
```
