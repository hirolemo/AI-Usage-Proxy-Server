"""
AI Usage Proxy Server

A production-grade proxy server that sits between users and Ollama, providing:
- OpenAI-compatible API endpoints
- Token usage tracking per user
- Rate limiting and usage limits
- Admin controls
"""

import json
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import init_db
from app.middleware.auth import AuthMiddleware
from app.middleware.request_id import RequestIdMiddleware
from app.routers import completions_router, admin_router, usage_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - runs on startup and shutdown."""
    # Startup: Initialize database
    await init_db()
    print(f"Database initialized at {settings.database_path}")
    print(f"Proxy server ready. Forwarding requests to {settings.ollama_base_url}")

    yield

    # Shutdown: Cleanup if needed
    print("Shutting down...")


class PrettyJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, indent=2, ensure_ascii=False).encode("utf-8")


app = FastAPI(
    title="AI Usage Proxy Server",
    description="OpenAI-compatible proxy for Ollama with usage tracking and rate limiting",
    version="1.0.0",
    lifespan=lifespan,
    default_response_class=PrettyJSONResponse,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request ID middleware (before auth so request_id is available everywhere)
app.add_middleware(RequestIdMiddleware)

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(completions_router)
app.include_router(usage_router)
app.include_router(admin_router)

# Mount static files for demo UI
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "AI Usage Proxy Server",
        "ollama_url": settings.ollama_base_url,
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
