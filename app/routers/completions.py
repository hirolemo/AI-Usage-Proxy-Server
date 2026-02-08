from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import StreamingResponse
import json

from ..models.schemas import ChatCompletionRequest
from ..services.ollama_client import ollama_client
from ..services.token_tracker import token_tracker
from ..middleware.auth import get_current_user
from ..middleware.rate_limit import check_rate_limit, rate_limiter

router = APIRouter(prefix="/v1", tags=["completions"])


@router.post("/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(check_rate_limit),
):
    """
    Create a chat completion (OpenAI-compatible endpoint).

    Supports both streaming and non-streaming responses.
    """
    user_id = current_user["id"]

    try:
        if request.stream:
            # Streaming response
            async def generate():
                stream = ollama_client.chat_completion_stream(request)
                tracked_stream = token_tracker.track_streaming_response(
                    user_id=user_id,
                    model=request.model,
                    stream=stream,
                )

                prompt_tokens = 0
                completion_tokens = 0

                async for chunk in tracked_stream:
                    yield chunk

                    # Extract tokens from final chunk for rate limiter
                    if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                        try:
                            data = json.loads(chunk[6:])
                            if "usage" in data and data["usage"]:
                                total = data["usage"].get("total_tokens", 0)
                                if total > 0:
                                    rate_limiter.record_tokens(user_id, total)
                        except (json.JSONDecodeError, KeyError):
                            pass

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            # Non-streaming response
            response = await ollama_client.chat_completion(request)

            # Track usage
            await token_tracker.track_from_response(
                user_id=user_id,
                model=request.model,
                response=response,
            )

            # Update rate limiter with token count
            total_tokens = response.get("usage", {}).get("total_tokens", 0)
            if total_tokens > 0:
                rate_limiter.record_tokens(user_id, total_tokens)

            return response

    except Exception as e:
        if "connect" in str(e).lower():
            raise HTTPException(
                status_code=503,
                detail="Unable to connect to Ollama server. Please ensure Ollama is running.",
            )
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def list_models(
    current_user: dict = Depends(get_current_user),
):
    """List available models (proxy to Ollama)."""
    import httpx
    from ..config import get_settings

    settings = get_settings()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            data = response.json()

        # Transform to OpenAI format
        models = []
        for model in data.get("models", []):
            models.append({
                "id": model.get("name", ""),
                "object": "model",
                "created": 0,
                "owned_by": "ollama",
            })

        return {"object": "list", "data": models}

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unable to fetch models: {str(e)}")
