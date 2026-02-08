import time
from collections import defaultdict
from dataclasses import dataclass, field
from fastapi import HTTPException, Request

from ..database import (
    get_rate_limits,
    get_requests_in_window,
    get_tokens_in_window,
    get_total_tokens,
)


@dataclass
class WindowCounter:
    """Sliding window counter for rate limiting."""
    timestamps: list[float] = field(default_factory=list)
    token_counts: list[tuple[float, int]] = field(default_factory=list)

    def add_request(self, tokens: int = 0) -> None:
        """Record a new request."""
        now = time.time()
        self.timestamps.append(now)
        if tokens > 0:
            self.token_counts.append((now, tokens))

    def get_request_count(self, window_seconds: int) -> int:
        """Get number of requests in the last N seconds."""
        now = time.time()
        cutoff = now - window_seconds
        # Clean old entries
        self.timestamps = [ts for ts in self.timestamps if ts > cutoff]
        return len(self.timestamps)

    def get_token_count(self, window_seconds: int) -> int:
        """Get total tokens in the last N seconds."""
        now = time.time()
        cutoff = now - window_seconds
        # Clean old entries
        self.token_counts = [(ts, tokens) for ts, tokens in self.token_counts if ts > cutoff]
        return sum(tokens for _, tokens in self.token_counts)


class RateLimiter:
    """
    Sliding window rate limiter.

    Uses in-memory counters for fast checks with DB fallback for accuracy.
    """

    def __init__(self):
        # In-memory counters per user
        self._counters: dict[str, WindowCounter] = defaultdict(WindowCounter)

    def _get_counter(self, user_id: str) -> WindowCounter:
        """Get or create a counter for a user."""
        return self._counters[user_id]

    async def check_rate_limit(self, user_id: str) -> None:
        """
        Check if a request is allowed under rate limits.

        Raises HTTPException with 429 status if rate limit exceeded.
        """
        limits = await get_rate_limits(user_id)
        if not limits:
            return  # No limits configured

        counter = self._get_counter(user_id)

        # Check requests per minute
        if limits["requests_per_minute"]:
            requests_per_minute = counter.get_request_count(60)
            if requests_per_minute >= limits["requests_per_minute"]:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded: {limits['requests_per_minute']} requests per minute",
                        "retry_after": 60,
                    },
                    headers={"Retry-After": "60"},
                )

        # Check requests per day
        if limits["requests_per_day"]:
            requests_per_day = await get_requests_in_window(user_id, 86400)
            if requests_per_day >= limits["requests_per_day"]:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded: {limits['requests_per_day']} requests per day",
                        "retry_after": 3600,
                    },
                    headers={"Retry-After": "3600"},
                )

        # Check tokens per minute
        if limits["tokens_per_minute"]:
            tokens_per_minute = counter.get_token_count(60)
            if tokens_per_minute >= limits["tokens_per_minute"]:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded: {limits['tokens_per_minute']} tokens per minute",
                        "retry_after": 60,
                    },
                    headers={"Retry-After": "60"},
                )

        # Check tokens per day
        if limits["tokens_per_day"]:
            tokens_per_day = await get_tokens_in_window(user_id, 86400)
            if tokens_per_day >= limits["tokens_per_day"]:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded: {limits['tokens_per_day']} tokens per day",
                        "retry_after": 3600,
                    },
                    headers={"Retry-After": "3600"},
                )

        # Check total token limit
        if limits["total_token_limit"]:
            total_tokens = await get_total_tokens(user_id)
            if total_tokens >= limits["total_token_limit"]:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": f"Total token limit exceeded: {limits['total_token_limit']} tokens",
                        "retry_after": None,
                    },
                )

        # Record the request attempt
        counter.add_request()

    def record_tokens(self, user_id: str, tokens: int) -> None:
        """Record token usage for rate limiting."""
        counter = self._get_counter(user_id)
        # Add to token counts (timestamp already recorded by add_request)
        now = time.time()
        counter.token_counts.append((now, tokens))


# Dependency for routes
async def check_rate_limit(request: Request) -> None:
    """FastAPI dependency to check rate limits."""
    if not hasattr(request.state, "user") or not request.state.user:
        return  # Auth middleware will handle this

    user_id = request.state.user["id"]
    await rate_limiter.check_rate_limit(user_id)


# Singleton instance
rate_limiter = RateLimiter()
