import json
from typing import AsyncGenerator

from ..database import record_usage, get_usage_stats, calculate_cost


class TokenTracker:
    """Service for tracking token usage."""

    async def track_usage(
        self,
        user_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        request_id: str | None = None,
    ) -> None:
        """Record token usage for a request."""
        total_tokens = prompt_tokens + completion_tokens

        # Calculate cost based on model pricing
        cost = await calculate_cost(model, prompt_tokens, completion_tokens)

        await record_usage(
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            request_id=request_id,
        )

    async def track_from_response(
        self,
        user_id: str,
        model: str,
        response: dict,
    ) -> None:
        """Extract and track usage from an OpenAI-format response."""
        usage = response.get("usage", {})
        await self.track_usage(
            user_id=user_id,
            model=model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )

    async def track_streaming_response(
        self,
        user_id: str,
        model: str,
        stream: AsyncGenerator[str, None],
    ) -> AsyncGenerator[str, None]:
        """
        Wrap a streaming response to track usage from the final chunk.

        Yields chunks as-is while accumulating usage info.
        """
        prompt_tokens = 0
        completion_tokens = 0

        async for chunk in stream:
            yield chunk

            # Try to extract usage from chunk
            if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
                try:
                    data = json.loads(chunk[6:])
                    if "usage" in data and data["usage"]:
                        prompt_tokens = data["usage"].get("prompt_tokens", 0)
                        completion_tokens = data["usage"].get("completion_tokens", 0)
                except (json.JSONDecodeError, KeyError):
                    pass

        # Record usage after stream completes
        if prompt_tokens > 0 or completion_tokens > 0:
            await self.track_usage(
                user_id=user_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

    async def get_user_usage(self, user_id: str) -> dict:
        """Get usage statistics for a user."""
        return await get_usage_stats(user_id)


# Singleton instance
token_tracker = TokenTracker()
