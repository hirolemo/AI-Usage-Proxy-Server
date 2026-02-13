import base64
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

from ..models.schemas import ChatCompletionRequest, ChatMessage, ContentPart, ImageUrl
from ..services.ollama_client import ollama_client, OllamaError
from ..services.token_tracker import token_tracker
from ..middleware.auth import get_current_user
from ..middleware.rate_limit import check_rate_limit, rate_limiter
from ..config import get_settings, ALLOWED_MODELS

router = APIRouter(prefix="/v1", tags=["completions"])

PROMPT_PREVIEW_MAX_LENGTH = 200


def _extract_prompt_preview(messages: list) -> str | None:
    """Extract a truncated preview from the last user message."""
    # Iterate in reverse to find the most recent user message
    for msg in reversed(messages):
        role = msg.role if hasattr(msg, "role") else msg.get("role")
        if role != "user":
            continue

        content = msg.content if hasattr(msg, "content") else msg.get("content")
        if content is None:
            continue

        # Simple string content
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            # Multipart content (vision messages) — join text parts
            text_parts = []
            for part in content:
                part_type = part.type if hasattr(part, "type") else part.get("type")
                if part_type == "text":
                    part_text = part.text if hasattr(part, "text") else part.get("text", "")
                    text_parts.append(part_text)
            text = " ".join(text_parts).strip() if text_parts else "[image]"
        else:
            continue

        if not text:
            continue

        if len(text) > PROMPT_PREVIEW_MAX_LENGTH:
            return text[:PROMPT_PREVIEW_MAX_LENGTH] + "..."
        return text

    return None


def _check_unsupported_features(request: ChatCompletionRequest) -> list[dict]:
    """Check for unsupported OpenAI features and return warnings."""
    warnings = []

    if request.tools:
        warnings.append({
            "type": "unsupported_parameter",
            "param": "tools",
            "message": "Tool calling is not supported by this proxy",
        })

    if request.tool_choice:
        warnings.append({
            "type": "unsupported_parameter",
            "param": "tool_choice",
            "message": "Tool choice is not supported by this proxy",
        })

    if request.logprobs:
        warnings.append({
            "type": "unsupported_parameter",
            "param": "logprobs",
            "message": "Log probabilities are not supported by this proxy",
        })

    if request.logit_bias:
        warnings.append({
            "type": "unsupported_parameter",
            "param": "logit_bias",
            "message": "Logit bias is not supported by this proxy",
        })

    return warnings


async def _handle_completion(
    request: ChatCompletionRequest,
    user_id: str,
):
    """
    Shared completion handler for both JSON and upload endpoints.
    """
    # Check for unsupported features and generate warnings
    warnings = _check_unsupported_features(request)

    # Extract prompt preview for request history
    prompt_preview = _extract_prompt_preview(request.messages)

    if request.stream:
        # Streaming response
        async def generate():
            stream = ollama_client.chat_completion_stream(request)
            tracked_stream = token_tracker.track_streaming_response(
                user_id=user_id,
                model=request.model,
                stream=stream,
                prompt_preview=prompt_preview,
            )

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
            prompt_preview=prompt_preview,
        )

        # Update rate limiter with token count
        total_tokens = response.get("usage", {}).get("total_tokens", 0)
        if total_tokens > 0:
            rate_limiter.record_tokens(user_id, total_tokens)

        # Add warnings if any
        if warnings:
            response["warnings"] = warnings

        return response


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
        return await _handle_completion(request, user_id)
    except OllamaError as e:
        # Structured error response
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error": {
                    "message": e.message,
                    "type": e.error_type,
                    "param": e.param,
                }
            },
        )
    except Exception:
        logger.exception("Unexpected error in chat completion")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": "Internal server error",
                    "type": "server_error",
                }
            },
        )


@router.post("/chat/completions/upload")
async def create_chat_completion_with_upload(
    model: str = Form(...),
    messages: str = Form(...),
    stream: bool = Form(False),
    files: list[UploadFile] = File(default=[]),
    temperature: float | None = Form(None),
    max_tokens: int | None = Form(None),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(check_rate_limit),
):
    """
    Create a chat completion with file uploads.

    Accepts multipart form data with image files that will be converted to base64
    and injected into the last user message.
    """
    user_id = current_user["id"]
    settings = get_settings()

    try:
        # Parse messages from JSON string
        try:
            messages_list = json.loads(messages)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in messages field")

        # Validate and convert files to base64 data URLs
        image_contents = []
        for file in files:
            # Validate file type
            if file.content_type not in settings.allowed_image_types:
                raise HTTPException(
                    status_code=415,
                    detail=f"Unsupported file type: {file.content_type}. Allowed types: {', '.join(settings.allowed_image_types)}",
                )

            # Read file
            file_data = await file.read()

            # Validate file size
            file_size_mb = len(file_data) / (1024 * 1024)
            if file_size_mb > settings.max_upload_size_mb:
                raise HTTPException(
                    status_code=413,
                    detail=f"File {file.filename} exceeds maximum size of {settings.max_upload_size_mb}MB",
                )

            # Convert to base64 data URL
            encoded = base64.b64encode(file_data).decode("utf-8")
            data_url = f"data:{file.content_type};base64,{encoded}"
            image_contents.append(ImageUrl(url=data_url))

        # Inject images into the last user message
        if image_contents and messages_list:
            # Find the last user message
            last_user_idx = None
            for i in range(len(messages_list) - 1, -1, -1):
                if messages_list[i].get("role") == "user":
                    last_user_idx = i
                    break

            if last_user_idx is not None:
                last_msg = messages_list[last_user_idx]

                # Convert content to list of parts if it's a string
                if isinstance(last_msg.get("content"), str):
                    text_content = last_msg["content"]
                    content_parts = [ContentPart(type="text", text=text_content)]
                else:
                    content_parts = last_msg.get("content", [])

                # Add image parts
                for img in image_contents:
                    content_parts.append(ContentPart(type="image_url", image_url=img))

                messages_list[last_user_idx]["content"] = content_parts

        # Build ChatCompletionRequest
        chat_messages = []
        for msg in messages_list:
            chat_messages.append(ChatMessage(**msg))

        request = ChatCompletionRequest(
            model=model,
            messages=chat_messages,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Delegate to shared completion handler
        return await _handle_completion(request, user_id)

    except HTTPException:
        raise
    except OllamaError as e:
        # Structured error response
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error": {
                    "message": e.message,
                    "type": e.error_type,
                    "param": e.param,
                }
            },
        )
    except Exception:
        logger.exception("Unexpected error in chat completion")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": "Internal server error",
                    "type": "server_error",
                }
            },
        )


@router.get("/models")
async def list_models(
    current_user: dict = Depends(get_current_user),
):
    """List available models (proxy to Ollama)."""
    settings = get_settings()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            data = response.json()

        # Transform to OpenAI format
        models = []
        for model in data.get("models", []):
            name = model.get("name", "")
            if name.endswith(":latest"):
                name = name[:-7]
            if name not in ALLOWED_MODELS:
                continue
            models.append({
                "id": name,
                "object": "model",
                "created": 0,
                "owned_by": "ollama",
            })

        # Ensure all allowed models are always present
        present_ids = {m["id"] for m in models}
        for allowed in ALLOWED_MODELS:
            if allowed not in present_ids:
                models.append({
                    "id": allowed,
                    "object": "model",
                    "created": 0,
                    "owned_by": "ollama",
                })

        return {"object": "list", "data": models}

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unable to fetch models: {str(e)}")
