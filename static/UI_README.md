# AI Usage Proxy Demo UI

A clean, responsive web interface for the AI Usage Proxy Server.

## Accessing the UI

Once the server is running, open your browser to:
```
http://localhost:8000/static/index.html
```

## Features

### 1. Chat Panel
- **Real-time streaming**: Watch tokens appear as they're generated
- **Model selection**: Choose from available Ollama models
- **Stream toggle**: Switch between streaming and non-streaming responses
- **Message history**: View your conversation with chat bubbles
- **Image upload** (Phase 2): Upload images for vision models (when backend is available)

### 2. Usage Panel
- **Token statistics**: View total requests, tokens used (prompt/completion/total)
- **Cost tracking** (Phase 2): See total costs when billing backend is implemented
- **Per-model breakdown**: Detailed usage stats for each model
- **Pricing history** (Phase 2): Timeline of rate changes

### 3. Admin Panel
- **User management**: Create and delete users
- **API key generation**: Get API keys for new users
- **Rate limits**: Configure per-user limits (requests/tokens per minute/day)
- **Pricing management** (Phase 2): Set per-model input/output costs
- **Change history** (Phase 2): Audit log of pricing changes

## Usage

### Getting Started
1. **Enter API Key**: Paste your API key in the header (format: `sk-userid-xxxxx`)
2. **Select Model**: Choose a model from the dropdown
3. **Start Chatting**: Type your message and click Send

### Admin Features
1. **Enter Admin Key**: Paste the admin key (default: `admin-secret-key`)
2. **Create Users**: Navigate to Admin panel and create new users
3. **Configure Limits**: Set rate limits for each user
4. **Manage Pricing** (Phase 2): Set per-model costs when available

## Error Handling

The UI provides visual feedback for all scenarios:
- **Red toasts**: Errors (invalid keys, rate limits, backend issues)
- **Green toasts**: Success (user created, pricing updated)
- **Yellow toasts**: Warnings (missing fields)

All toasts auto-dismiss after 5 seconds.

### Common Errors
- **401 Unauthorized**: Invalid API key or admin key
- **429 Rate Limited**: You've hit a rate limit (wait for cooldown)
- **502 Bad Gateway**: Ollama is not running or unreachable
- **404 Not Found**: Model doesn't exist

## Phase 2 Features (Progressive Enhancement)

The UI gracefully handles missing Phase 2 backend features:

### Current State (Phase 1 Complete)
- ✅ Chat completions (streaming + non-streaming)
- ✅ Model selection
- ✅ Token usage tracking
- ✅ User management
- ✅ Rate limit configuration

### Phase 2 (Backend Required)
- ⏳ **Cost tracking**: Cost column hidden until backend adds `total_cost` to responses
- ⏳ **Image upload**: Upload button disabled until `/v1/chat/completions/upload` endpoint exists
- ⏳ **Pricing management**: Section hidden until `/admin/pricing` endpoints are available

The UI automatically detects Phase 2 feature availability by:
1. Checking for `total_cost` field in usage responses (shows cost cards/columns)
2. Testing `/admin/pricing` endpoint (shows pricing management section)

## Security Notes

- **API keys stored in memory only**: Not persisted to localStorage for security
- **Keys cleared on page refresh**: You'll need to re-enter them
- **No session management**: Each API call includes the Bearer token

## Responsive Design

The UI works on:
- Desktop (1400px+)
- Tablet (768px - 1400px)
- Mobile (< 768px)

On mobile, the sidebar converts to horizontal tabs.

## Browser Compatibility

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+

Requires support for:
- `fetch()` API
- `ReadableStream` (for SSE streaming)
- ES6+ JavaScript features

## Development

The UI is built with:
- **Vanilla JavaScript** (no frameworks)
- **Modern CSS** (CSS Grid, Flexbox, CSS Variables)
- **Fetch API** for HTTP requests
- **ReadableStream** for SSE streaming

Files:
- `index.html` - Structure and layout
- `app.js` - API calls, state management, DOM manipulation
- `style.css` - Styling and responsive design
