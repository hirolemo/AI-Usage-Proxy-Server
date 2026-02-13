import asyncio
import base64
import httpx
import json
import time
from typing import AsyncGenerator

from ..config import get_settings
from ..models.schemas import ChatCompletionRequest, ContentPart

settings = get_settings()


class OllamaError(Exception):
    """Base exception for Ollama client errors."""

    def __init__(self, message: str, error_type: str = "server_error", status_code: int = 502, param: str | None = None):
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.param = param
        super().__init__(message)


class OllamaClient:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.timeout = httpx.Timeout(120.0, connect=10.0)
        self._client: httpx.AsyncClient | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def startup(self):
        """Initialize shared HTTP client and concurrency semaphore."""
        max_concurrent = settings.ollama_max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(timeout=self.timeout)
        print(f"Max concurrent Ollama requests: {max_concurrent}")

    async def shutdown(self):
        """Close the shared HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _transform_request(self, request: ChatCompletionRequest) -> dict:
        """Transform OpenAI-format request to Ollama format."""
        messages = []
        for msg in request.messages:
            if isinstance(msg.content, str):
                messages.append({"role": msg.role, "content": msg.content})
            else:
                # Handle multimodal content (vision)
                text_parts = []
                images = []

                for part in msg.content:
                    if isinstance(part, dict):
                        part = ContentPart(**part)

                    if part.type == "text" and part.text:
                        text_parts.append(part.text)
                    elif part.type == "image_url" and part.image_url:
                        image_data = self._process_image(part.image_url.url)
                        if image_data:
                            images.append(image_data)

                message = {
                    "role": msg.role,
                    "content": " ".join(text_parts) if text_parts else "",
                }
                if images:
                    message["images"] = images
                messages.append(message)

        payload = {
            "model": request.model,
            "messages": messages,
            "stream": request.stream,
        }

        # Add optional parameters
        options = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if request.top_p is not None:
            options["top_p"] = request.top_p
        if request.stop is not None:
            if isinstance(request.stop, str):
                options["stop"] = [request.stop]
            else:
                options["stop"] = request.stop

        if options:
            payload["options"] = options

        # Handle response_format
        if request.response_format and request.response_format.type == "json_object":
            payload["format"] = "json"

        return payload

    def _process_image(self, url: str) -> str | None:
        """Process image URL to base64 for Ollama."""
        if url.startswith("data:"):
            # Already base64 data URL
            # Format: data:image/jpeg;base64,/9j/4AAQ...
            try:
                _, data = url.split(",", 1)
                return data
            except ValueError:
                return None
        else:
            # External URL - fetch and convert to base64
            try:
                response = httpx.get(url, timeout=30.0, follow_redirects=True)
                response.raise_for_status()
                return base64.b64encode(response.content).decode("utf-8")
            except Exception:
                return None

    async def chat_completion(self, request: ChatCompletionRequest) -> dict:
        """Send a non-streaming chat completion request to Ollama."""
        payload = self._transform_request(request)
        payload["stream"] = False

        try:
            async with self._semaphore:
                response = await self._client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            # Transform Ollama response to OpenAI format
            return self._transform_response(data, request.model)

        except httpx.HTTPStatusError as e:
            # Map Ollama errors to structured errors
            if e.response.status_code == 404:
                raise OllamaError(
                    message=f"Model '{request.model}' not found",
                    error_type="invalid_request_error",
                    status_code=404,
                    param="model",
                )
            elif e.response.status_code == 400:
                raise OllamaError(
                    message="Invalid request to Ollama",
                    error_type="invalid_request_error",
                    status_code=400,
                )
            elif e.response.status_code >= 500:
                raise OllamaError(
                    message="Ollama server error",
                    error_type="server_error",
                    status_code=502,
                )
            else:
                raise OllamaError(
                    message=f"Ollama request failed: {e.response.status_code}",
                    error_type="server_error",
                    status_code=502,
                )
        except httpx.RequestError as e:
            raise OllamaError(
                message="Unable to connect to Ollama server",
                error_type="server_error",
                status_code=503,
            )

    async def chat_completion_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[str, None]:
        """Send a streaming chat completion request to Ollama."""
        payload = self._transform_request(request)
        payload["stream"] = True

        try:
            async with self._semaphore:
                async with self._client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=payload,
                ) as response:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        # Map Ollama errors to structured errors
                        if e.response.status_code == 404:
                            error_chunk = {
                                "error": {
                                    "message": f"Model '{request.model}' not found",
                                    "type": "invalid_request_error",
                                    "param": "model",
                                }
                            }
                        elif e.response.status_code == 400:
                            error_chunk = {
                                "error": {
                                    "message": "Invalid request to Ollama",
                                    "type": "invalid_request_error",
                                }
                            }
                        else:
                            error_chunk = {
                                "error": {
                                    "message": "Ollama server error",
                                    "type": "server_error",
                                }
                            }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    try:
                        async for line in response.aiter_lines():
                            if not line:
                                continue

                            try:
                                chunk_data = json.loads(line)
                                # Check stream_options for usage inclusion
                                include_usage = True
                                if request.stream_options:
                                    include_usage = request.stream_options.include_usage

                                transformed = self._transform_stream_chunk(
                                    chunk_data, request.model, include_usage
                                )
                                yield f"data: {json.dumps(transformed)}\n\n"

                                # Check if this is the final chunk
                                if chunk_data.get("done", False):
                                    yield "data: [DONE]\n\n"
                                    return
                            except json.JSONDecodeError:
                                continue

                    except Exception as e:
                        # Mid-stream error handling
                        error_chunk = {
                            "error": {
                                "message": "Stream interrupted",
                                "type": "server_error",
                            }
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

        except httpx.RequestError as e:
            # Connection error before stream starts
            error_chunk = {
                "error": {
                    "message": "Unable to connect to Ollama server",
                    "type": "server_error",
                }
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
            yield "data: [DONE]\n\n"
            return

    def _transform_response(self, ollama_response: dict, model: str) -> dict:
        """Transform Ollama response to OpenAI format."""

        message = ollama_response.get("message", {})

        # Calculate usage from eval_count and prompt_eval_count
        prompt_tokens = ollama_response.get("prompt_eval_count", 0)
        completion_tokens = ollama_response.get("eval_count", 0)

        return {
            "id": f"chatcmpl-{ollama_response.get('created_at', '')}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": message.get("role", "assistant"),
                        "content": message.get("content", ""),
                    },
                    "finish_reason": "stop" if ollama_response.get("done") else None,
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    def _transform_stream_chunk(self, ollama_chunk: dict, model: str, include_usage: bool = True) -> dict:
        """Transform Ollama streaming chunk to OpenAI format."""

        message = ollama_chunk.get("message", {})
        is_done = ollama_chunk.get("done", False)

        chunk = {
            "id": f"chatcmpl-{ollama_chunk.get('created_at', '')}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": message.get("role") if not is_done else None,
                        "content": message.get("content", "") if not is_done else None,
                    },
                    "finish_reason": "stop" if is_done else None,
                }
            ],
        }

        # Include usage in final chunk if requested
        if is_done and include_usage:
            prompt_tokens = ollama_chunk.get("prompt_eval_count", 0)
            completion_tokens = ollama_chunk.get("eval_count", 0)
            chunk["usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }

        return chunk


# Singleton instance
ollama_client = OllamaClient()
