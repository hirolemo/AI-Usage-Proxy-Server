# AI Usage Proxy Server: Design Write-Up

## Overview

I included this write-up to demonstrate my thought-process and better organize my thoughts and decisions. Hope this helps paint the big picture in my journey working through this exercise. It was an enjoyable experience!

High Level Flow
```
Client (OpenAI SDK) ──> Proxy Server (Port 8000) ──> Ollama (Port 11434)
                              │
                              v
                        SQLite DB (Usage/Auth/Billing)
```

## Implementation Requirements

- OpenAI-compatible `/v1/chat/completions` endpoint (streaming + non-streaming)
- Vision processing with moondream (base64 and URL images)
- OpenAI SDK used in integration tests to prove proxy compatibility
- Handles concurrent users and hundreds of requests/second
- Billing and usage limiting to prevent excessive cost
- User-facing API showing token usage across models
- Admin API to set short (per-minute), long (per-day), and total rate limits
- Server returns 429 errors when limits are hit

### Bonus Features

- Admin UI: view usage and billing for all users, manage pricing and rate limits
- User UI: see usage by model and model pricing
- Chat section with real-time streaming, model selection, and image upload

---

## Tech Stack & Why

| Technology | Role | Why |
|---|---|---|
| **FastAPI** | Web framework | Async-native, built-in Pydantic validation, auto-generated OpenAPI docs. The async model maps directly to handling concurrent proxy requests without blocking. |
| **httpx** | HTTP client to Ollama | Async support + streaming (`aiter_lines`). The only Python HTTP client that cleanly supports async streaming in both directions. |
| **SQLite + aiosqlite** | Database | Zero-ops, single-file deployment. WAL mode + connection pooling (20 connections) gives us the concurrency we need for a single-server demo. |
| **Pydantic** | Request/response validation | First-class FastAPI integration. Lets us define OpenAI-compatible schemas once and get validation + serialization for free. |
| **pydantic-settings** | Configuration | Loads from env vars or `.env` file with type validation. |

**Why not Postgres?** I decided to go with SQLite for this project scope. A single-server proxy doesn't really require a separate database process. If horizontal scaling were needed, I would swap to Postgres is straightforward. The `aiosqlite` abstraction keeps DB logic in one module (`app/database.py`).

---

## Design Decisions & Tradeoffs

### 1. API Key Format: `sk-{user_id}-{random}`

The key embeds the user ID, so the auth middleware can extract it without a DB lookup on every request. In practice we still validate against the DB (the key could be revoked), but this format makes keys human-readable for debugging.

**Tradeoff:** The user ID is visible in the key. Acceptable for an internal proxy — these aren't being shared publicly.

### 2. Sliding Window Rate Limiting (not Fixed Window)

Fixed-window rate limiting has a boundary exploit: a user can send `2x` their limit by timing requests at the window boundary (end of one window + start of the next). A 'sliding window' method eliminates this.

**Implementation:** In-memory `WindowCounter` per user for fast per-minute checks (no DB hit), with DB fallback for per-day and total limits. The in-memory counters self-clean on each check by pruning expired timestamps.

**Tradeoff:** In-memory counters reset on server restart. I found this to be acceptable because the DB is the source of truth for daily/total limits, and per-minute counters repopulate within 60 seconds.

### 3. Separate `/upload` Endpoint for Image Files

Two options: make the existing `/v1/chat/completions` accept both JSON and multipart, or create a separate `/v1/chat/completions/upload` endpoint.

**Chose separate endpoint.** FastAPI can't cleanly validate a single route for both JSON body and multipart form data. The separate endpoint keeps the OpenAI SDK-compatible JSON path untouched. The upload endpoint parses a JSON string from the `messages` form field, validates files (type + size), converts to base64 data URIs, injects images into the last user message, and delegates to the `_handle_completion()` handler (shared with chat completion).

**Tradeoff:** The UI needs to know which endpoint to call. But the upload endpoint is only used by the UI and direct file upload use cases, not the OpenAI SDK.

### 4. Cost Baked Into Usage Records at Request Time

When a completion request finishes, `token_tracker.track_usage()` calls `calculate_cost()` using the current model pricing and stores the cost alongside the usage record. If pricing is later updated, old records keep the cost that was active when the request was made.

**Why:** This is correct for billing — the user is charged the rate at the time of service. This also helped me avoid expensive retroactive recalculation.

### 5. Admin-Set Per-Model Pricing

Pricing is set via admin CRUD endpoints (`/admin/pricing`), split into input and output cost per million tokens (matching industry standard — prompt tokens are cheaper than completion tokens). Since we're proxying to local Ollama, there's no actual cost. The "cost" is synthetic — useful for simulating a real billing system.

**Tradeoff:** If no pricing is set for a model, cost is silently $0. There's no enforcement or warning. The `pricing_history` table displayed to admins is acts as an audit log.

### 6. SSE Streaming Matching OpenAI Format

Streaming responses use Server-Sent Events with `data: {json}\n\n` framing, terminated by `data: [DONE]\n\n`. This is byte-for-byte compatible with the OpenAI SDK's streaming parser.

For token counting during streaming: Ollama provides `prompt_eval_count` and `eval_count` in the final chunk. We extract these and calculate cost after the stream completes. This avoids estimation — we get exact counts from Ollama.

**`stream_options.include_usage` support:** Clients can send `stream_options: { include_usage: true }` to get token counts in the final streaming chunk (standard OpenAI feature). We default to including usage since Ollama always provides it.

### 7. Concurrency Control with Semaphore & SQLite Connection Pooling

The Ollama client uses an `asyncio.Semaphore` (configurable via `OLLAMA_MAX_CONCURRENT`, default 1) to limit concurrent requests to Ollama. This prevents overloading a single GPU instance while letting the proxy itself handle unlimited concurrent connections.

A pool of 20 SQLite connections. WAL mode allows concurrent reads during writes. The pool is initialized at startup and connections are reused across requests, avoiding the overhead of opening/closing connections per query. Provides concurrent DB access for hundreds of users (encountered limitations during load testing, so pivoted to this).

### 8. Static Demo UI Served by FastAPI

I created a basic UI with Vanilla JS and no React to better demo the admin and user APIs. All under the `/static` directory: `index.html`, `app.js`, `style.css`.

**Auth bypass for `/static`:** The auth middleware skips static file paths. Anyone who can reach the server can load the UI, but the UI itself requires entering an API key to make any API calls. API keys are stored in memory only (not localStorage) — prevents XSS from stealing persisted keys. Downside: key is lost on page refresh.

**UI panels:**
- **Chat:** Model selector, streaming toggle, message history with chat bubbles, image upload
- **Usage:** Total tokens, total cost, per-model breakdown table, pricing info, request history with pagination
- **Admin:** Create/delete users, rate limit configuration, pricing management with change history

Error states surface via color-coded toast notifications (red for errors, green for success, yellow for warnings, auto-dismiss after 5s). Rate limit 429s show the specific limit hit. Invalid keys disable the relevant panels.

### 9. Structured Error Responses

For API calls using curl commands, errors match OpenAI's format: `{"error": {"message": "...", "type": "invalid_request_error", "param": "model"}}`. The Ollama client maps HTTP status codes (404 → model not found, 400 → invalid request, 5xx → server error) to structured `OllamaError` exceptions. Mid-stream errors yield an error chunk before `[DONE]` so the client always gets a clean stream termination.

### 10. `X-Request-Id` Middleware

Every request gets a UUID (or uses the client-provided `X-Request-Id` header). Returned in the response header for correlation. Stored in usage records for debugging.

### 11. `response_format` Passthrough

Clients can send `response_format: { type: "json_object" }` (standard OpenAI feature). We map this to Ollama's `format: "json"` parameter.

---

## All APIs

### User Endpoints (require `Authorization: Bearer <api_key>`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/v1/chat/completions` | Chat completion (streaming + non-streaming) |
| POST | `/v1/chat/completions/upload` | Chat completion with image file upload |
| GET | `/v1/models` | List available models |
| GET | `/v1/usage` | Get your token usage |
| GET | `/v1/usage/summary` | Usage aggregated by model |
| GET | `/v1/usage/history` | Paginated request history |
| GET | `/v1/pricing` | View current model pricing |

### Admin Endpoints (require `Authorization: Bearer <admin_api_key>`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/admin/users` | Create user |
| GET | `/admin/users` | List all users |
| GET | `/admin/users/{user_id}` | Get user details |
| DELETE | `/admin/users/{user_id}` | Delete user |
| DELETE | `/admin/users` | Delete all users |
| GET | `/admin/users/{user_id}/usage` | Get user's usage stats |
| GET | `/admin/users/{user_id}/limits` | Get user's rate limits |
| PUT | `/admin/users/{user_id}/limits` | Update user's rate limits |
| POST | `/admin/pricing` | Set model pricing |
| GET | `/admin/pricing` | List all model pricing |
| GET | `/admin/pricing/{model}` | Get pricing for one model |
| PUT | `/admin/pricing/{model}` | Update pricing |
| DELETE | `/admin/pricing/{model}` | Remove pricing |
| GET | `/admin/pricing/history/all` | Full pricing change history |
| GET | `/admin/pricing/history/{model}` | Pricing history for one model |

### Public Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Service status |
| GET | `/health` | Health check |
| GET | `/static/index.html` | Demo UI |

---

## Database Schema

Five tables:

- **`users`** — TEXT primary key (self-documenting IDs, URL-safe), API key, created timestamp
- **`usage`** — Per-request records: user, model, prompt/completion/total tokens, cost, request_id, prompt_preview, timestamp. Enables auditing, rate limiting, and billing from a single table.
- **`rate_limits`** — Per-user limits: requests per minute/day, tokens per minute/day, total token limit
- **`model_pricing`** — Single row per model: input/output cost per million tokens. Fast lookup for cost calculation.
- **`pricing_history`** — Append-only audit log of all pricing changes

Migrations (adding `cost`, `request_id`, `prompt_preview` columns to `usage`) use idempotent `ALTER TABLE` wrapped in try/except — safe for re-runs.

---

## Proving Hundreds of RPS & Concurrent Users Work

### The Problem

With a real Ollama instance, each chat completion takes 18–106 seconds of actual LLM inference. With 100 users all queuing into a single Ollama instance, the proxy wasn't able to keep up. Hundreds of RPS through real inference was unachievable — that's an Ollama bottleneck, not a proxy bottleneck. I had to introduce a mock Ollama instance with a fast completion time to better test the proxy server's throughput and handling of concurrent users.

### Strategy 1: Hit Non-Ollama Endpoints at Scale

```bash
# Health check baseline (no auth, no DB)
hey -n 10000 -c 200 http://localhost:8000/health

# Auth + DB read (usage endpoint) — proves auth middleware + SQLite scale
hey -n 5000 -c 100 -H "Authorization: Bearer <api_key>" http://localhost:8000/v1/usage

# Models endpoint (auth + Ollama metadata, fast)
hey -n 5000 -c 100 -H "Authorization: Bearer <api_key>" http://localhost:8000/v1/models
```

### Strategy 2: Mock Ollama for Full-Pipeline Benchmarks

Stand up a fake Ollama (`mock_ollama.py`) that responds instantly, so we benchmark the proxy's full request pipeline: **auth → rate limiting → forwarding → token tracking → DB write → response**.

```bash
# Terminal 1: mock Ollama
python3 mock_ollama.py

# Terminal 2: proxy (points to localhost:11434)
python3 main.py

# Terminal 3: blast it
hey -n 5000 -c 200 \
  -m POST \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:1b","messages":[{"role":"user","content":"hi"}],"stream":false}' \
  http://localhost:8000/v1/chat/completions
```

The mock removes the Ollama bottleneck so we're measuring the proxy's real work. This is how we demonstrate the proxy can handle hundreds/thousands of RPS.

### Strategy 3: Locust

```bash
TEST_API_KEY=<api_key> locust -f tests/test_load.py \
  --host=http://localhost:8000 --users 200 --spawn-rate 20 --run-time 60s --headless
```

Web UI for live graphs: `http://localhost:8089`

### What These Prove

| Metric | What It Proves |
|---|---|
| RPS on `/v1/chat/completions` with mock Ollama | Proxy throughput ceiling |
| p99 latency on auth endpoints | Auth + rate limit overhead is minimal |
| 200+ concurrent users all getting responses | Async architecture works |
| Rate-limited user gets 429 while others succeed | Per-user isolation works |
| Send N requests, `/v1/usage` shows exactly N | DB tracking is reliable under concurrency |

---

## Running Tests

```bash
# Unit tests (no Ollama needed)
pytest tests/test_basic.py -v

# Integration tests (requires Ollama running + server running on port 8000)
pytest tests/test_streaming.py tests/test_vision.py -v -s

# Quick load test (requires running server)
TEST_API_KEY=<api_key> python tests/test_load.py
```

Integration tests use the OpenAI Python SDK pointed at `http://localhost:8000/v1` to prove the proxy is a drop-in replacement for the OpenAI API.
